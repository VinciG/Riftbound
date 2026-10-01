import os
import json
import subprocess
import urllib.request
import urllib.error
from datetime import datetime
from html import escape

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

def git_show(path):
    try:
        return subprocess.run(
            ["git", "show", f"HEAD:{path}"],
            capture_output=True, text=True, check=True
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

def load_json(path, from_git=False):
    if from_git:
        raw = git_show(path)
        if raw is None:
            return None
        return json.loads(raw)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def compare_tcgplayer_prices(old_data, new_data):
    old_sets = (old_data or {}).get("sets", {})
    new_sets = (new_data or {}).get("sets", {})
    old_total = sum(len(cards) for cards in old_sets.values())
    new_total = sum(len(cards) for cards in new_sets.values())
    lines = [f"💵 TCGplayer Market (USD): {new_total} cartas con precio ({'+' if new_total >= old_total else ''}{new_total - old_total} vs último feed)"]

    if not old_data:
        return "\n".join(lines)

    for set_id in sorted(set(old_sets) | set(new_sets)):
        old_set = old_sets.get(set_id, {})
        new_set = new_sets.get(set_id, {})
        old_keys, new_keys = set(old_set), set(new_set)
        added, removed = new_keys - old_keys, old_keys - new_keys
        changed = {key for key in old_keys & new_keys if old_set[key].get("market") != new_set[key].get("market")}
        parts = []
        if added: parts.append(f"+{len(added)} nuevas")
        if removed: parts.append(f"-{len(removed)} eliminadas")
        if changed: parts.append(f"~{len(changed)} cambiadas")
        if not parts:
            continue

        lines.append(f"\n▫ {set_id}: {', '.join(parts)}")
        for key in sorted(changed):
            old_market = old_set[key].get("market", {})
            new_market = new_set[key].get("market", {})
            card_name = escape(new_set[key].get("name") or key)
            variants = []
            for variant in sorted(set(old_market) | set(new_market)):
                before, after = old_market.get(variant), new_market.get(variant)
                before_text = f"${before:.2f}" if before is not None else "sin dato"
                after_text = f"${after:.2f}" if after is not None else "sin dato"
                variants.append(f"{escape(variant)}: {before_text} → {after_text}")
            lines.append(f"  🔹 {card_name}: {'; '.join(variants)}")
        for key in sorted(added):
            market = new_set[key].get("market", {})
            prices = " / ".join(f"{name} ${value:.2f}" for name, value in sorted(market.items()))
            lines.append(f"  ➕ {escape(new_set[key].get('name') or key)}: {prices} (nuevo precio)")
        for key in sorted(removed):
            lines.append(f"  ➖ {escape(old_set[key].get('name') or key)} (sin precio en el feed)")
    return "\n".join(lines)

def compare_cartas(old, new):
    lines = []
    if old == new:
        return None
    old_sets = old.get("sets", {}) if old else {}
    new_sets = new.get("sets", {}) if new else {}

    # Detect new sets
    for name in new_sets:
        if name not in old_sets:
            s = new_sets[name]
            lines.append(f"🆕 Nuevo set: {name} ({s.get('total', '?')} cartas)")

    for name in old_sets:
        if name not in new_sets:
            lines.append(f"🗑 Set eliminado: {name}")

    for name in new_sets:
        if name in old_sets:
            o, n = old_sets[name], new_sets[name]
            diff_fields = []
            for f in ["total", "total_base", "total_ovr", "legend_count", "cartas_reveladas"]:
                ov, nv = o.get(f), n.get(f)
                if ov != nv:
                    diff_fields.append(f"{f}: {ov} → {nv}")
            if diff_fields:
                lines.append(f"  ▫ {name}: {', '.join(diff_fields)}")

    # Detect pull rate changes
    old_pr = old.get("pull_rates", {}) if old else {}
    new_pr = new.get("pull_rates", {}) if new else {}
    if old_pr != new_pr:
        lines.append(f"  ▫ Pull rates: actualizados")

    if lines:
        return "📋 cartas.json:\n" + "\n".join(lines)
    return None

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID no configurados. Saltando notificación.")
        return False
    # Split into chunks if too long (Telegram limit ~4000 chars)
    MAX = 4000
    parts_send = [message[i:i+MAX] for i in range(0, len(message), MAX)]
    for chunk in parts_send:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = json.dumps({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp.read()
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            print(f"❌ Error Telegram HTTP {e.code}: {body}")
            return False
        except Exception as e:
            print(f"❌ Error enviando Telegram: {e}")
            return False
    print(f"✅ Notificación enviada por Telegram ({len(parts_send)} parte(s))")
    return True

def main():
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("ℹ️ Telegram no configurado. Solo se mostrará el resumen en consola.")

    old_tcg_prices = load_json("tcgplayer_prices.json", from_git=True)
    new_tcg_prices = load_json("tcgplayer_prices.json")
    old_cartas = load_json("cartas.json", from_git=True)
    new_cartas = load_json("cartas.json")

    parts = []
    parts.append(f"<b>🔄 Riftbound — Actualización {datetime.utcnow().strftime('%d %b %Y %H:%M UTC')}</b>\n")

    if old_tcg_prices != new_tcg_prices:
        parts.append(compare_tcgplayer_prices(old_tcg_prices, new_tcg_prices))
    else:
        parts.append("💵 TCGplayer Market: sin cambios")

    cartas_diff = compare_cartas(old_cartas, new_cartas)
    if cartas_diff:
        parts.append("")
        parts.append(cartas_diff)

    message = "\n".join(parts)

    print("\n" + "=" * 50)
    print("RESUMEN DE CAMBIOS:")
    print("=" * 50)
    print(message)
    print("=" * 50 + "\n")

    send_telegram(message)

if __name__ == "__main__":
    main()
