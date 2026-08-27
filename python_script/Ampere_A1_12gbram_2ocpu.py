import os
import sys
import tempfile
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
    print(" MENYEMAK KUNCI & SPESIFIKASI CONFIGURATION OCI")
    print("=" * 60)

    tenancy = get_env_var(["OCI_TENANCY", "TENANCY", "tenancy"])
    user = get_env_var(["OCI_USER", "USER", "user"])
    fingerprint = get_env_var(["OCI_FINGERPRINT", "FINGERPRINT", "fingerprint"])
    region = get_env_var(["OCI_REGION", "REGION", "region"], "ap-singapore-1")
    key_file = get_env_var(["OCI_KEY_FILE", "KEY_FILE", "key_file"])
    key_content = get_env_var(["OCI_KEY_CONTENT", "OCI_PRIVATE_KEY", "KEY_CONTENT"])
    compartment_id = get_env_var(["OCI_COMPARTMENT_ID", "COMPARTMENT_ID"]) or tenancy
    subnet_id = get_env_var(["OCI_SUBNET_ID", "SUBNET_ID"])
    ssh_public_key = get_env_var(["OCI_SSH_PUBLIC_KEY", "SSH_PUBLIC_KEY"])

    # Semakan tempatan jika OCI_KEY_FILE tidak diset oleh GitHub Actions
    if not key_file and not key_content:
        local_key_path = "kunci_oci/oci-oracle-api-key/braderdin007@gmail.com-2026-07-26T17_31_09.593Z.pem"
        if os.path.exists(local_key_path):
            key_file = local_key_path

    print(f"✓ Tenancy OCID       : {tenancy[:15]}...{tenancy[-5:] if tenancy else ''}")
    print(f"✓ User OCID          : {user[:15]}...{user[-5:] if user else ''}")
    print(f"✓ Fingerprint        : {fingerprint}")
    print(f"✓ Region             : {region}")
    print(f"✓ Key File Path      : {key_file if key_file else 'Key Content String'}")

    config = {
        "user": user,
        "fingerprint": fingerprint,
        "tenancy": tenancy,
        "region": region,
    }

    if key_file and os.path.exists(key_file):
        config["key_file"] = key_file
    elif key_content:
        key_str = key_content.strip('"\'').replace("\\n", "\n")
        tmp_key = tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.pem')
        tmp_key.write(key_str)
        tmp_key.close()
        config["key_file"] = tmp_key.name

    return {
        "config": config,
        "compartment_id": compartment_id,
        "subnet_id": subnet_id,
        "ssh_public_key": ssh_public_key
    }


def find_ubuntu_arm_image(compute_client, compartment_id):
    print("[INFO] Mencari Image Ubuntu ARM (aarch64) secara automatik...")
    try:
        images = compute_client.list_images(
            compartment_id=compartment_id,
            operating_system="Canonical Ubuntu",
            shape="VM.Standard.A1.Flex",
            sort_by="TIMECREATED",
            sort_order="DESC"
        ).data

        for img in images:
            if "aarch64" in img.operating_system_version.lower() or "arm" in img.display_name.lower() or "ubuntu" in img.display_name.lower():
                print(f"[SUCCESS] Dijumpai Image Ubuntu ARM: {img.display_name}")
                return img.id
        if images:
            print(f"[SUCCESS] Menggunakan Image fallback: {images[0].display_name}")
            return images[0].id
    except Exception as e:
        print(f"[RALAT] Gagal mendapatkan senarai image Ubuntu: {str(e)}")
    return None


def find_default_subnet(network_client, compartment_id):
    print("[INFO] Mencari Subnet sedia ada secara automatik...")
    try:
        subnets = network_client.list_subnets(compartment_id=compartment_id).data
        if subnets:
            print(f"[SUCCESS] Subnet dijumpai: {subnets[0].display_name}")
            return subnets[0].id
    except Exception as e:
        print(f"[RALAT] Gagal mencari Subnet: {str(e)}")
    return None


def run_sniper():
    env_data = validate_config()
    if not env_data:
        sys.exit(1)

    config = env_data["config"]
    compartment_id = env_data["compartment_id"]
    subnet_id = env_data["subnet_id"]
    ssh_public_key = env_data["ssh_public_key"]

    try:
        identity_client = oci.identity.IdentityClient(config)
        compute_client = oci.core.ComputeClient(config)
        network_client = oci.core.VirtualNetworkClient(config)
    except Exception as e:
        print(f"❌ [RALAT AUTENTIKASI OCI SDK]: {str(e)}")
        sys.exit(1)

    print("[INFO] Meminta senarai Availability Domains (AD)...")
    try:
        ads = identity_client.list_availability_domains(compartment_id=config['tenancy']).data
    except Exception as e:
        print(f"❌ [RALAT GET AD]: {str(e)}")
        sys.exit(1)

    if not subnet_id:
        subnet_id = find_default_subnet(network_client, compartment_id)

    image_id = find_ubuntu_arm_image(compute_client, compartment_id)
    if not image_id:
        print("❌ [RALAT KRITIKAL]: Image ID Ubuntu ARM tidak dijumpai.")
        sys.exit(1)

    shape = "VM.Standard.A1.Flex"
    ocpus = 2.0
    memory_in_gbs = 12.0
    boot_volume_size_gbs = 200

    print("\n" + "=" * 60)
    print(" MENJALANKAN TEMBAKAN PERMOHONAN SLOT VM ARM ALWAYS FREE")
    print(f" Target Shape   : {shape}")
    print(f" OCPU           : {ocpus}")
    print(f" RAM            : {memory_in_gbs} GB")
    print(f" Boot Volume    : {boot_volume_size_gbs} GB (Ubuntu OS)")
    print("=" * 60)

    for ad in ads:
        ad_name = ad.name
        print(f"\n[TRY] Mencuba memohon slot di AD: {ad_name}...")

        metadata = {}
        if ssh_public_key:
            metadata["ssh_authorized_keys"] = ssh_public_key

        launch_details = oci.core.models.LaunchInstanceDetails(
            display_name="OCI-ARM-2OCPU-12GB-Ubuntu",
            compartment_id=compartment_id,
            availability_domain=ad_name,
            shape=shape,
            shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(
                ocpus=ocpus,
                memory_in_gbs=memory_in_gbs
            ),
            source_details=oci.core.models.InstanceSourceViaImageDetails(
                image_id=image_id,
                boot_volume_size_in_gbs=boot_volume_size_gbs
            ),
            create_vnic_details=oci.core.models.CreateVnicDetails(
                subnet_id=subnet_id,
                assign_public_ip=True
            ),
            metadata=metadata
        )

        try:
            response = compute_client.launch_instance(launch_details)
            print("🎉" * 20)
            print(f" BERJAYA! Instance ID: {response.data.id}")
            print("🎉" * 20)
            break
        except oci.exceptions.ServiceError as se:
            if se.status == 500 or "OutOfCapacity" in se.code or "Out of host capacity" in str(se.message):
                print(f"⚠️  [FULL SLOT] Kapasiti penuh di {ad_name}. Status: {se.status} - {se.code}")
            elif se.status == 429:
                print(f"⚠️  [RATE LIMIT] Terlalu banyak permintaan (Too Many Requests). Status: 429")
            else:
                print(f"❌ [RALAT SERVIS OCI ({se.status})]: Code: {se.code} | Message: {se.message}")
        except Exception as ex:
            print(f"❌ [RALAT TIDAK DIJANGKA]: {str(ex)}")


if __name__ == "__main__":
    run_sniper()
