"""Build a static TCGplayer market-price cache from TCGCSV's public feed."""

import json
import re
import sys
import time
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


TCGCSV_ROOT = "https://tcgcsv.com/tcgplayer"
DOTGG_API_URL = "https://api.dotgg.gg/cgfw/getcards?game=riftbound&mode=indexed"
USER_AGENT = "RiftboundPriceGuide/1.0 (https://github.com/VinciG/Riftbound)"
PRICE_FILE = Path("tcgplayer_prices.json")
ALIASES = {
    "VEN": "vendetta",  # TCGplayer abbreviation; the local catalog uses VND.
    "OGS": "origins",   # Proving Grounds cards are merged into Origins locally.
    "RWB": "t1_2025_worlds_champion_collection",
}
_last_request_at = 0.0


def _get_json(url):
    global _last_request_at
    delay = 0.12 - (time.monotonic() - _last_request_at)
    if delay > 0:
        time.sleep(delay)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    _last_request_at = time.monotonic()
    if isinstance(payload, dict) and payload.get("success") is False:
        raise RuntimeError(f"Feed returned an error for {url}: {payload.get('errors')}")
    return payload


def _get_text(url):
    global _last_request_at
    delay = 0.12 - (time.monotonic() - _last_request_at)
    if delay > 0:
        time.sleep(delay)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read().decode("utf-8").strip()
    _last_request_at = time.monotonic()
    return payload


def _clean_number(value):
    """Normalize a collector number while preserving letters and signature marks."""
    value = str(value or "").strip().lower().split("/", 1)[0]
    value = re.sub(r"\s+", "", value)
    match = re.fullmatch(r"([a-z]*)(\d+)([a-z]*\*?)", value)
    if not match:
        return value or None
    prefix, digits, suffix = match.groups()
    return f"{prefix}{int(digits)}{suffix}"


def _number_from_api_id(card_id):
    card_id = str(card_id or "").strip().lower()
    match = re.search(r"(?:^|[-\s])([a-z]?\d{1,3}[a-z]?\*?)(?=$|[-/\s])", card_id)
    if not match:
        return None
    number = match.group(1)
    if card_id.endswith("-star"):
        number += "*"
    return _clean_number(number)


def _number_from_product(product):
    for item in product.get("extendedData") or []:
        if str(item.get("name", "")).strip().lower() in ("number", "card number"):
            return _clean_number(item.get("value"))
    return None


def _normalized_name(value):
    value = str(value or "").lower()
    value = re.sub(r"\((?:alternate art|alt.?art|overnumbered|signature|foil|showcase|promo)[^)]*\)", " ", value)
    return "".join(character for character in value if character.isalnum())


def _set_code_map(sets):
    by_code = {}
    by_name = {}
    for set_name, set_data in sets.items():
        set_id = set_data.get("id")
        if not set_id:
            continue
        code = str(set_data.get("abbr", "")).upper()
        if code:
            by_code[code] = set_id
        by_name[re.sub(r"[^a-z0-9]", "", set_name.lower())] = set_id
        by_name[re.sub(r"[^a-z0-9]", "", str(set_id).lower())] = set_id
    by_code.update(ALIASES)
    return by_code, by_name


def _group_set_id(group, by_code, by_name):
    abbreviation = str(group.get("abbreviation", "")).upper()
    if abbreviation in by_code:
        return by_code[abbreviation]
    group_name = str(group.get("name", ""))
    normalized = re.sub(r"[^a-z0-9]", "", group_name.lower())
    if normalized in by_name:
        return by_name[normalized]
    if ":" in group_name:
        parent = re.sub(r"[^a-z0-9]", "", group_name.split(":", 1)[0].lower())
        return by_name.get(parent)
    return None


def _make_price_key(api_id, set_id, sets):
    key = str(api_id or "").lower()
    if key.endswith("-star"):
        key = key[:-5] + "*"
    for set_data in sets.values():
        if set_data.get("id") == set_id:
            total_base = set_data.get("total_base", 0)
            if total_base:
                key = f"{key}-{total_base}"
            break
    return key


def _catalog_indexes(rows, names, sets, set_name_map):
    by_set_number = defaultdict(lambda: defaultdict(list))
    for row in rows:
        card = dict(zip(names, row))
        set_id = set_name_map.get(card.get("set_name", ""))
        card_id = card.get("id", "")
        number = _number_from_api_id(card_id)
        if not set_id or not number:
            continue
        by_set_number[set_id][number].append({
            "id": _make_price_key(card_id, set_id, sets),
            "name": card.get("name", ""),
        })
    return by_set_number


def _match_product(product, set_id, by_set_number):
    number = _number_from_product(product)
    candidates = list(by_set_number.get(set_id, {}).get(number, [])) if number else []
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    product_name = _normalized_name(product.get("cleanName") or product.get("name"))
    exact = [card for card in candidates if _normalized_name(card["name"]) == product_name]
    if len(exact) == 1:
        return exact[0]
    contained = [card for card in candidates if _normalized_name(card["name"]) in product_name or product_name in _normalized_name(card["name"])]
    return contained[0] if len(contained) == 1 else None


def update_tcgplayer_prices(rows, names, sets, set_name_map):
    """Refresh TCGplayer market prices, preserving the last good file on feed errors."""
    by_code, by_name = _set_code_map(sets)
    by_set_number = _catalog_indexes(rows, names, sets, set_name_map)
    try:
        last_updated = _get_text("https://tcgcsv.com/last-updated.txt")
        if PRICE_FILE.exists() and last_updated:
            try:
                cached = json.loads(PRICE_FILE.read_text(encoding="utf-8"))
                minimum_cached_sets = min(3, len(by_set_number))
                if (cached.get("updated_at") == last_updated
                        and len(cached.get("sets", {})) >= minimum_cached_sets
                        and minimum_cached_sets > 0):
                    print("ℹ️ TCGCSV no tiene una versión nueva; se conserva la caché actual.")
                    return True
            except (json.JSONDecodeError, OSError):
                pass
        categories = _get_json(f"{TCGCSV_ROOT}/categories").get("results", [])
        category = next((item for item in categories if "riftbound" in str(item.get("name", "")).lower()), None)
        if not category:
            raise RuntimeError("Riftbound category not found in TCGCSV")
        groups = _get_json(f"{TCGCSV_ROOT}/{category['categoryId']}/groups").get("results", [])
    except Exception as error:
        print(f"⚠️ TCGplayer prices unavailable; keeping previous file: {error}")
        return False

    relevant = []
    for group in groups:
        set_id = _group_set_id(group, by_code, by_name)
        if set_id and by_set_number.get(set_id):
            relevant.append((group, set_id))

    if not relevant:
        print("⚠️ No TCGplayer groups matched the current card catalog; keeping previous file.")
        return False

    output_sets = defaultdict(dict)
    matched = set()
    try:
        for group, set_id in relevant:
            group_id = group.get("groupId")
            products = _get_json(f"{TCGCSV_ROOT}/{category['categoryId']}/{group_id}/products").get("results", [])
            prices = _get_json(f"{TCGCSV_ROOT}/{category['categoryId']}/{group_id}/prices").get("results", [])
            prices_by_product = defaultdict(list)
            for price in prices:
                if price.get("marketPrice") is not None:
                    try:
                        value = float(price["marketPrice"])
                    except (TypeError, ValueError):
                        continue
                    if value > 0:
                        prices_by_product[str(price.get("productId"))].append((str(price.get("subTypeName") or "Normal"), value))

            for product in products:
                variants = prices_by_product.get(str(product.get("productId")), [])
                if not variants:
                    continue
                card = _match_product(product, set_id, by_set_number)
                if not card:
                    continue
                key = card["id"]
                number = _number_from_product(product) or ""
                entry = output_sets[set_id].setdefault(key, {
                    "name": card["name"],
                    "number": number,
                    "market": {},
                    "url": product.get("url", ""),
                })
                for variant, value in variants:
                    entry["market"][variant] = value
                if product.get("url"):
                    entry["url"] = product["url"]
                matched.add((set_id, key))
    except Exception as error:
        print(f"⚠️ TCGplayer feed failed during import; keeping previous file: {error}")
        return False

    matched_sets = {set_id for set_id, _ in matched}
    minimum_matched_sets = min(3, len({set_id for _, set_id in relevant}))
    if len(matched) < 20 or len(matched_sets) < minimum_matched_sets:
        print(f"⚠️ Only {len(matched)} TCGplayer cards across {len(matched_sets)} sets matched; keeping previous file.")
        return False

    payload = {
        "source": "TCGplayer Market via TCGCSV",
        "currency": "USD",
        "updated_at": last_updated or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sets": dict(output_sets),
    }
    temporary = PRICE_FILE.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(PRICE_FILE)
    print(f"✅ 'tcgplayer_prices.json' actualizado ({len(matched)} cartas con market price).")
    return True


def main():
    try:
        sets_db = json.loads(Path("cartas.json").read_text(encoding="utf-8"))
        sets = sets_db.get("sets", {})
        request = urllib.request.Request(DOTGG_API_URL, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = json.loads(response.read().decode("utf-8"))
        set_name_map = {}
        for row in raw["data"]:
            card = dict(zip(raw["names"], row))
            set_name = card.get("set_name", "")
            set_id = str(set_name).lower().replace(" ", "_")
            if set_id in {"proving_grounds", "origins_proving_grounds", "arcane_box_set"}:
                set_id = "origins"
            if set_name and any(data.get("id") == set_id for data in sets.values()):
                set_name_map[set_name] = set_id
        if not update_tcgplayer_prices(raw["data"], raw["names"], sets, set_name_map):
            raise SystemExit(1)
    except Exception as error:
        print(f"❌ TCGplayer price import failed: {error}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
