import os
import json
import subprocess
import urllib.request
import urllib.error
from datetime import datetime

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

def compare_prices(old, new):
    lines = []
    total_old = sum(len(v) for v in old.values()) if old else 0
    total_new = sum(len(v) for v in new.values()) if new else 0
    lines.append(f"📦 Precios: {total_new} cartas con precio ({'+' if total_new >= total_old else ''}{total_new - total_old} vs ayer)")

    if old and new:
        for set_id in sorted(set(list(old.keys()) + list(new.keys()))):
            old_set = old.get(set_id, {})
            new_set = new.get(set_id, {})
            old_keys = set(old_set.keys())
            new_keys = set(new_set.keys())
            added = new_keys - old_keys
            removed = old_keys - new_keys
            changed = {k for k in old_keys & new_keys if old_set[k] != new_set[k]}
            parts = []
            if added:
                parts.append(f"+{len(added)} nuevas")
            if removed:
                parts.append(f"-{len(removed)} eliminadas")
            if changed:
                parts.append(f"~{len(changed)} cambiadas")
            if parts:
                lines.append(f"  ▫ {set_id}: {', '.join(parts)}")
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
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
        print("✅ Notificación enviada por Telegram")
        return True
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"❌ Error Telegram HTTP {e.code}: {body}")
        return False
    except Exception as e:
        print(f"❌ Error enviando Telegram: {e}")
        return False

def main():
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("ℹ️ Telegram no configurado. Solo se mostrará el resumen en consola.")

    old_prices = load_json("cardmarket_prices.json", from_git=True)
    new_prices = load_json("cardmarket_prices.json")
    old_cartas = load_json("cartas.json", from_git=True)
    new_cartas = load_json("cartas.json")

    parts = []
    parts.append(f"<b>🔄 Riftbound — Actualización {datetime.utcnow().strftime('%d %b %Y %H:%M UTC')}</b>\n")

    if old_prices != new_prices:
        parts.append(compare_prices(old_prices, new_prices))
    else:
        parts.append("📦 Precios: sin cambios")

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
