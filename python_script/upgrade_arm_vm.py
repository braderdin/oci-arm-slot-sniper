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


def run_upgrade():
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
    except Exception as e:
        print(f"❌ [RALAT AUTENTIKASI OCI SDK]: {e}")
        sys.exit(1)

    try:
        instances = compute_client.list_instances(compartment_id=compartment_id).data
        active_vms = [
            i for i in instances 
            if i.shape == "VM.Standard.A1.Flex" and i.lifecycle_state in ["RUNNING", "PROVISIONING", "STARTING"]
        ]

        if not active_vms:
            print("❌ [RALAT]: Tiada VM ARM aktif dijumpai untuk dinaik taraf.")
            sys.exit(1)

        target_vm = active_vms[0]
        target_ocpus = 2.0
        target_memory_gbs = 12.0

        update_details = oci.core.models.UpdateInstanceDetails(
            shape_config=oci.core.models.UpdateInstanceShapeConfigDetails(
                ocpus=target_ocpus,
                memory_in_gbs=target_memory_gbs
            )
        )

        print(f"🎯 [MENCUBA UPGRADE] Mengemaskini VM '{target_vm.display_name}' ke {target_ocpus} OCPU / {target_memory_gbs} GB RAM...")

        response = compute_client.update_instance(target_vm.id, update_details)
        print("🎉" * 20)
        print(f" 🎉 [BERJAYA!] Spesifikasi VM ARM berjaya dinaik taraf ke 2 OCPU / 12 GB RAM!")
        print(f" 🆔 Instance ID: {response.data.id}")
        print("🎉" * 20)
        sys.exit(0)

    except oci.exceptions.ServiceError as se:
        if se.status == 500 or "OutOfCapacity" in se.code or "Out of host capacity" in str(se.message):
            print(f"⚠️  [FULL SLOT] Kapasiti 2 OCPU / 12 GB RAM belum dibuka oleh host. Status: {se.status}")
        elif se.status == 429:
            print(f"⚠️  [RATE LIMIT] Terlalu banyak permintaan (Too Many Requests). Status: 429")
        else:
            print(f"❌ [RALAT SERVIS OCI ({se.status})]: Code: {se.code} | Message: {se.message}")
    except Exception as ex:
        print(f"❌ [RALAT TIDAK DIJANGKA]: {str(ex)}")


if __name__ == "__main__":
    run_upgrade()