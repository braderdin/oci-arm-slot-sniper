import os
import sys
import json
import tempfile
import urllib.request
import urllib.parse
from dotenv import load_dotenv

try:
    if os.path.exists(".env.local"):
        load_dotenv(".env.local", override=True)
    elif os.path.exists(".env"):
        load_dotenv(".env", override=True)
except ImportError:
    pass

try:
    import oci
except ImportError:
    print("[RALAT KRITIKAL] Pustaka 'oci' belum dipasang.")
    sys.exit(1)

print("=" * 60)
print(" MENYEMAK STATUS VM OCI & PEMBERITAHUAN TELEGRAM")
print("=" * 60)


def get_env_var(keys, default=None):
    if isinstance(keys, str):
        keys = [keys]
    for key in keys:
        val = os.getenv(key)
        if val and val.strip():
            return val.strip()
    return default


tenancy = get_env_var(["OCI_TENANCY", "TENANCY", "tenancy"])
user = get_env_var(["OCI_USER", "USER", "user"])
fingerprint = get_env_var(["OCI_FINGERPRINT", "FINGERPRINT", "fingerprint"])
region = get_env_var(["OCI_REGION", "REGION", "region"], "ap-singapore-1")
key_file = get_env_var(["OCI_KEY_FILE", "KEY_FILE", "key_file"])
key_content = get_env_var(["OCI_KEY_CONTENT", "OCI_PRIVATE_KEY", "KEY_CONTENT"])
compartment_id = get_env_var(["OCI_COMPARTMENT_ID", "COMPARTMENT_ID"]) or tenancy

bot_token = get_env_var(["TELEGRAM_BOT_TOKEN"])
chat_id = get_env_var(["TELEGRAM_CHAT_ID"])

# Semakan fail kunci tempatan jika tidak diset di environment
if not key_file and not key_content:
    local_key_path = "kunci_oci/oci-oracle-api-key/braderdin007@gmail.com-2026-07-26T17_31_09.593Z.pem"
    if os.path.exists(local_key_path):
        key_file = local_key_path

def send_telegram(message):
    if not bot_token or not chat_id:
        print("⚠️ [AMARAN TELEGRAM]: Token/Chat ID tiada, mesej tidak dihantar.")
        return False
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

# Autentikasi OCI Configuration
config = {
    "user": user,
    "fingerprint": fingerprint,
    "tenancy": tenancy,
    "region": region
}

if key_file and os.path.exists(key_file):
    config["key_file"] = key_file
elif key_content:
    key_str = key_content.strip('"\'').replace("\\n", "\n")
    tmp_key = tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.pem')
    tmp_key.write(key_str)
    tmp_key.close()
    config["key_file"] = tmp_key.name
else:
    err_msg = "❌ *RALAT OCI AUTH*: Fail/String Private Key tidak dijumpai!"
    print(err_msg)
    send_telegram(err_msg)
    sys.exit(1)

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
