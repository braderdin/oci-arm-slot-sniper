import os
import sys
import subprocess
import tempfile
from dotenv import load_dotenv

if os.path.exists(".env.local"):
    load_dotenv(".env.local", override=True)
elif os.path.exists(".env"):
    load_dotenv(".env", override=True)

try:
    import oci
except ImportError:
    print("[RALAT KRITIKAL] Pustaka 'oci' belum dipasang.")
    sys.exit(1)


def decrypt_gpg(gpg_file_path, passphrase):
    if not os.path.exists(gpg_file_path):
        return None
    try:
        cmd = [
            "gpg", "--batch", "--yes", "--quiet",
            "--passphrase", passphrase,
            "--decrypt", gpg_file_path
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except Exception as e:
        print(f"❌ [RALAT DECRYPT GPG] {gpg_file_path}: {e}")
        return None


def get_env_var(keys, default=None):
    if isinstance(keys, str):
        keys = [keys]
    for key in keys:
        val = os.getenv(key)
        if val and val.strip():
            return val.strip()
    return default


def validate_config():
    print("=" * 60)
    print(" MENYEMAK KUNCI GPG & AUTENTIKASI OCI (AMD MICRO)")
    print("=" * 60)

    tenancy = get_env_var(["OCI_TENANCY", "TENANCY", "tenancy"])
    user = get_env_var(["OCI_USER", "USER", "user"])
    fingerprint = get_env_var(["OCI_FINGERPRINT", "FINGERPRINT", "fingerprint"])
    region = get_env_var(["OCI_REGION", "REGION", "region"], "ap-singapore-1")
    compartment_id = get_env_var(["OCI_COMPARTMENT_ID", "COMPARTMENT_ID"]) or tenancy
    subnet_id = get_env_var(["OCI_SUBNET_ID", "SUBNET_ID"])
    gpg_passphrase = get_env_var(["GPG_PASSPHRASE", "PASSPHRASE"])

    if not gpg_passphrase:
        print("❌ [RALAT KRITIKAL] GPG_PASSPHRASE tiada dalam fail .env atau GitHub Secrets.")
        sys.exit(1)

    # 1. Decrypt API Key (.pem.gpg)
    api_gpg = "python_script/braderdin007@gmail.com-2026-07-26T17_31_09.593Z.pem.gpg"
    pem_content = decrypt_gpg(api_gpg, gpg_passphrase)
    if not pem_content:
        print("❌ Gagal menyahsulit API Key .pem.gpg!")
        sys.exit(1)

    tmp_key = tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.pem')
    tmp_key.write(pem_content)
    tmp_key.close()
    key_file_path = tmp_key.name
    print("✓ API Private Key (.pem.gpg) berjaya dinyahsulit.")

    # 2. Decrypt SSH Public Key (.pub.gpg)
    ssh_pub_gpg = "python_script/ssh-key-2026-07-27.key.pub.gpg"
    ssh_public_key = decrypt_gpg(ssh_pub_gpg, gpg_passphrase)
    if ssh_public_key:
        print("✓ SSH Public Key (.pub.gpg) berjaya dinyahsulit.")
    else:
        print("⚠️ SSH Public Key gagal dinyahsulit! VM akan dicipta tanpa akses SSH.")

    print(f"✓ Tenancy OCID       : {tenancy[:15]}...{tenancy[-5:] if tenancy else ''}")
    print(f"✓ User OCID          : {user[:15]}...{user[-5:] if user else ''}")
    print(f"✓ Fingerprint        : {fingerprint}")
    print(f"✓ Region             : {region}")

    config = {
        "user": user,
        "fingerprint": fingerprint,
        "tenancy": tenancy,
        "region": region,
        "key_file": key_file_path
    }

    return {
        "config": config,
        "compartment_id": compartment_id,
        "subnet_id": subnet_id,
        "ssh_public_key": ssh_public_key
    }


def find_default_subnet(network_client, compartment_id):
    try:
        vcns = network_client.list_vcns(compartment_id=compartment_id).data
        if vcns:
            subnets = network_client.list_subnets(compartment_id=compartment_id, vcn_id=vcns[0].id).data
            if subnets:
                return subnets[0].id
    except Exception as e:
        print(f"❌ [RALAT AUTO SUBNET]: {e}")
    return None


def find_ubuntu_amd_image(compute_client, compartment_id):
    try:
        images = compute_client.list_images(
            compartment_id=compartment_id,
            operating_system="Canonical Ubuntu",
            shape="VM.Standard.E2.1.Micro",
            sort_by="TIMECREATED",
            sort_order="DESC"
        ).data

        for img in images:
            name_lower = img.display_name.lower()
            if "24.04" in name_lower and "minimal" not in name_lower:
                return img.id

        for img in images:
            name_lower = img.display_name.lower()
            if "22.04" in name_lower and "minimal" not in name_lower:
                return img.id

        if images:
            return images[0].id
    except Exception as e:
        print(f"❌ [RALAT CARI IMAGE]: {e}")
    return None


def run_sniper():
    env_data = validate_config()
    config = env_data["config"]
    compartment_id = env_data["compartment_id"]
    subnet_id = env_data["subnet_id"]
    ssh_public_key = env_data["ssh_public_key"]

    try:
        oci.config.validate_config(config)
        identity_client = oci.identity.IdentityClient(config)
        compute_client = oci.core.ComputeClient(config)
        network_client = oci.core.VirtualNetworkClient(config)
    except Exception as e:
        print(f"❌ [RALAT AUTENTIKASI OCI SDK]: {e}")
        sys.exit(1)

    ads = identity_client.list_availability_domains(compartment_id=config['tenancy']).data
    ad_name = ads[0].name

    if not subnet_id:
        subnet_id = find_default_subnet(network_client, compartment_id)

    image_id = find_ubuntu_amd_image(compute_client, compartment_id)

    metadata = {}
    if ssh_public_key:
        metadata["ssh_authorized_keys"] = ssh_public_key

    instance_details = oci.core.models.LaunchInstanceDetails(
        compartment_id=compartment_id,
        availability_domain=ad_name,
        display_name="AlwaysFree-AMD-Micro",
        shape="VM.Standard.E2.1.Micro",
        source_details=oci.core.models.InstanceSourceViaImageDetails(
            image_id=image_id
        ),
        create_vnic_details=oci.core.models.CreateVnicDetails(
            subnet_id=subnet_id,
            assign_public_ip=True
        ),
        metadata=metadata
    )

    try:
        response = compute_client.launch_instance(instance_details)
        print(f"\n🎉 [BERJAYA!] VM AMD Micro baharu berjaya dicipta bersama kunci SSH!")
        print(f"Instance ID: {response.data.id}")
    except oci.exceptions.ServiceError as e:
        print(f"❌ [RALAT OCI SERVICE]: Status {e.status} - {e.code}: {e.message}")
    except Exception as e:
        print(f"❌ [RALAT UNKNOWN]: {e}")


if __name__ == "__main__":
    run_sniper()
