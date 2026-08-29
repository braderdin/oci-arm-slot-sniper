import os
import sys
from dotenv import load_dotenv

if os.path.exists(".env.local"):
    load_dotenv(".env.local", override=True)
elif os.path.exists(".env"):
    load_dotenv(".env", override=True)

try:
    import oci
except ImportError:
    print("❌ [RALAT KRITIKAL] Pustaka 'oci' belum dipasang.")
    sys.exit(1)


def get_env_var(keys, default=None):
    if isinstance(keys, str):
        keys = [keys]
    for key in keys:
        val = os.getenv(key)
        if val and val.strip():
            return val.strip()
    return default


def check_upgrade_status():
    tenancy = get_env_var(["OCI_TENANCY", "TENANCY", "tenancy"])
    user = get_env_var(["OCI_USER", "USER", "user"])
    fingerprint = get_env_var(["OCI_FINGERPRINT", "FINGERPRINT", "fingerprint"])
    region = get_env_var(["OCI_REGION", "REGION", "region"], "ap-singapore-1")
    key_file = get_env_var(["OCI_KEY_FILE", "KEY_FILE", "key_file"])
    compartment_id = get_env_var(["OCI_COMPARTMENT_ID", "COMPARTMENT_ID"]) or tenancy

    if not key_file or not os.path.exists(key_file):
        local_key = "kunci_oci/oci-oracle-api-key/braderdin007@gmail.com-2026-07-26T17_31_09.593Z.pem"
        if os.path.exists(local_key):
            key_file = local_key

    config = {
        "user": user,
        "fingerprint": fingerprint,
        "tenancy": tenancy,
        "region": region,
        "key_file": key_file
    }

    try:
        oci.config.validate_config(config)
        compute_client = oci.core.ComputeClient(config)

        print("=" * 65)
        print(" 🔍 [SEMAKAN PINTAR UPGRADE] Memeriksa status spesifikasi VM ARM...")
        print("=" * 65)

        instances = compute_client.list_instances(compartment_id=compartment_id).data
        active_states = ["RUNNING", "PROVISIONING", "STARTING"]

        arm_vms = [
            inst for inst in instances
            if inst.shape == "VM.Standard.A1.Flex" and inst.lifecycle_state in active_states
        ]

        if not arm_vms:
            print("⚠️ [AMARAN] Tiada VM ARM aktif dijumpai. Tembakan upgrade dibatalkan.")
            sys.exit(1)

        vm = arm_vms[0]
        current_ocpu = float(vm.shape_config.ocpus) if vm.shape_config else 0.0
        current_ram = float(vm.shape_config.memory_in_gbs) if vm.shape_config else 0.0

        print(f"📌 Nama VM       : {vm.display_name}")
        print(f"📌 Status VM     : {vm.lifecycle_state}")
        print(f"📌 OCPU Semasa   : {current_ocpu} OCPU")
        print(f"📌 RAM Semasa    : {current_ram} GB")
        print("=" * 65)

        # Semak jika sudah mencapai 2 OCPU / 12 GB RAM
        if current_ocpu >= 2.0 and current_ram >= 12.0:
            print("\n🛑 [VM SUDAH BERJAYA DI-UPGRADE!]")
            print(f"🎉 VM '{vm.display_name}' sudah berada pada spesifikasi {current_ocpu} OCPU / {current_ram} GB RAM.")
            print("✨ Step 2 (Tembakan Upgrade) dibatalkan secara automatik.\n")
            sys.exit(1)  # Menghentikan langkah seterusnya di GitHub Actions
        else:
            print(f"\n✅ VM ARM sedia ada dikesan ({current_ocpu} OCPU / {current_ram} GB RAM).")
            print("⚡ Meneruskan ke Step 2 untuk memulakan 20 percubaan upgrade...\n")
            sys.exit(0)  # Meneruskan ke Step 2 di GitHub Actions

    except Exception as e:
        print(f"⚠️ [AMARAN SEMAKAN]: Gagal menyemak status VM ({e}). Meneruskan tembakan upgrade...")
        sys.exit(0)


if __name__ == "__main__":
    check_upgrade_status()