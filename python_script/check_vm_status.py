import os
import sys
import json
import urllib.request
import urllib.parse
import oci
from dotenv import load_dotenv

load_dotenv('.env.local')

print("============================================================")
print(" MENYEMAK STATUS VM OCI & PEMBERITAHUAN TELEGRAM")
print("============================================================")

tenancy = os.getenv("OCI_TENANCY")
user = os.getenv("OCI_USER")
fingerprint = os.getenv("OCI_FINGERPRINT")
region = os.getenv("OCI_REGION")
key_content = os.getenv("OCI_KEY_CONTENT")
compartment_id = os.getenv("OCI_COMPARTMENT_ID") or tenancy

bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
chat_id = os.getenv("TELEGRAM_CHAT_ID")

if not bot_token or not chat_id:
    print("❌ [RALAT TELEGRAM]: TELEGRAM_BOT_TOKEN atau TELEGRAM_CHAT_ID tiada dalam .env.local!")
    sys.exit(1)

def send_telegram(message):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req) as response:
            return response.status == 200
    except Exception as e:
        print(f"❌ [RALAT TELEGRAM API]: {e}")
        return False

# Autentikasi OCI
key_str = key_content.strip('"\'').replace("\\n", "\n") if key_content else ""
config = {
    "user": user,
    "key_content": key_str,
    "fingerprint": fingerprint,
    "tenancy": tenancy,
    "region": region
}

try:
    compute_client = oci.core.ComputeClient(config)
    network_client = oci.core.VirtualNetworkClient(config)
except Exception as e:
    err_msg = f"❌ *RALAT OCI AUTH*: Gagal menyambung ke OCI SDK.\n`{e}`"
    print(err_msg)
    send_telegram(err_msg)
    sys.exit(1)

# Semak senarai VM
try:
    instances = compute_client.list_instances(compartment_id=compartment_id).data
    
    # Filter VM yang aktif (bukan TERMINATED)
    active_vms = [i for i in instances if i.lifecycle_state not in ["TERMINATED", "TERMINATING"]]
    
    if active_vms:
        msg = "🎉 *TAHNIAH! VM OCI BERJAYA DICIPTA!*\n\n"
        for vm in active_vms:
            # Ambil Public IP
            public_ip = "Tiada IP Awam"
            try:
                vnics = compute_client.list_vnic_attachments(compartment_id=compartment_id, instance_id=vm.id).data
                if vnics:
                    vnic = network_client.get_vnic(vnic_id=vnics[0].vnic_id).data
                    public_ip = vnic.public_ip or "Tiada IP Awam"
            except Exception:
                pass

            msg += f"🖥️ *Nama*: `{vm.display_name}`\n"
            msg += f"⚙️ *Shape*: `{vm.shape}`\n"
            msg += f"📊 *Status*: `{vm.lifecycle_state}`\n"
            msg += f"🌐 *IP Awam*: `{public_ip}`\n"
            msg += f"📍 *Region*: `{region}`\n"
            msg += "-----------------------------------\n"
        
        print("✓ VM Aktif dijumpai! Menghantar mesej kejayaan ke Telegram...")
        send_telegram(msg)
    else:
        msg = f"ℹ️ *Laporan Harian OCI Sniper*\n\n📍 *Region*: `{region}`\n📊 *Status*: Tiada VM aktif dijumpai lagi.\n🔄 *Skrip Sniper*: Masih menembak secara automatik..."
        print("✓ Tiada VM aktif. Menghantar laporan harian ke Telegram...")
        send_telegram(msg)

except Exception as e:
    err_msg = f"❌ *RALAT SEMAKAN VM*: {e}"
    print(err_msg)
    send_telegram(err_msg)
