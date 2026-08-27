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
    print(" MENYEMAK KUNCI & AUTENTIKASI OCI (AMD MICRO)")
    print("=" * 60)

    tenancy = get_env_var(["OCI_TENANCY", "TENANCY", "tenancy"])
    user = get_env_var(["OCI_USER", "USER", "user"])
    fingerprint = get_env_var(["OCI_FINGERPRINT", "FINGERPRINT", "fingerprint"])
    region = get_env_var(["OCI_REGION", "REGION", "region"], "ap-singapore-1")
    key_file = get_env_var(["OCI_KEY_FILE", "KEY_FILE", "key_file"])
    key_content = get_env_var(["OCI_KEY_CONTENT", "OCI_PRIVATE_KEY", "KEY_CONTENT"])
    compartment_id = get_env_var(["OCI_COMPARTMENT_ID", "COMPARTMENT_ID"]) or tenancy
    subnet_id = get_env_var(["OCI_SUBNET_ID", "SUBNET_ID"])

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
        "subnet_id": subnet_id
    }


def find_default_subnet(network_client, compartment_id):
    print("⚠️  [AMARAN] OCI_SUBNET_ID tiada. Mencari Subnet VCN secara automatik...")
    try:
        vcns = network_client.list_vcns(compartment_id=compartment_id).data
        if vcns:
            subnets = network_client.list_subnets(compartment_id=compartment_id, vcn_id=vcns[0].id).data
            if subnets:
                print(f"✓ Subnet dijumpai: {subnets[0].id}")
                return subnets[0].id
    except Exception as e:
        print(f"❌ [RALAT AUTO SUBNET]: {e}")
    return None


def find_ubuntu_amd_image(compute_client, compartment_id):
    print("[INFO] Mencari Image Ubuntu 22.04 Standard AMD (Bukan Minimal)...")
    try:
        images = compute_client.list_images(
            compartment_id=compartment_id,
            operating_system="Canonical Ubuntu",
            shape="VM.Standard.E2.1.Micro",
            sort_by="TIMECREATED",
            sort_order="DESC"
        ).data

        # 1. Cari Ubuntu 22.04 Standard (bukan minimal)
        for img in images:
            name_lower = img.display_name.lower()
            if "22.04" in name_lower and "minimal" not in name_lower:
                print(f"[SUCCESS] Dijumpai Image Ubuntu 22.04 Standard: {img.display_name}")
                return img.id

        # 2. Fallback: Cari Ubuntu 24.04 Standard (bukan minimal)
        for img in images:
            name_lower = img.display_name.lower()
            if "24.04" in name_lower and "minimal" not in name_lower:
                print(f"[SUCCESS] Dijumpai Image Ubuntu 24.04 Standard: {img.display_name}")
                return img.id

        # 3. Fallback: Mana-mana imej Ubuntu yang bukan Minimal
        for img in images:
            name_lower = img.display_name.lower()
            if "minimal" not in name_lower:
                print(f"[SUCCESS] Dijumpai Image Non-Minimal: {img.display_name}")
                return img.id

        if images:
            print(f"[SUCCESS] Menggunakan Image fallback: {images[0].display_name}")
            return images[0].id
    except Exception as e:
        print(f"❌ [RALAT CARI IMAGE]: {e}")
    return None


def run_sniper():
    env_data = validate_config()
    if not env_data:
        sys.exit(1)

    config = env_data["config"]
    compartment_id = env_data["compartment_id"]
    subnet_id = env_data["subnet_id"]

    try:
        oci.config.validate_config(config)
        identity_client = oci.identity.IdentityClient(config)
        compute_client = oci.core.ComputeClient(config)
        network_client = oci.core.VirtualNetworkClient(config)
        print("✓ Autentikasi Kunci OCI SDK: BERJAYA")
    except Exception as e:
        print(f"❌ [RALAT AUTENTIKASI OCI SDK]: {e}")
        sys.exit(1)

    try:
        ads = identity_client.list_availability_domains(compartment_id=config['tenancy']).data
        ad_name = ads[0].name
        print(f"✓ Availability Domain: {ad_name}")
    except Exception as e:
        print(f"❌ [RALAT GET AD]: {e}")
        sys.exit(1)

    if not subnet_id:
        subnet_id = find_default_subnet(network_client, compartment_id)
        if not subnet_id:
            print("❌ [RALAT SUBNET]: Subnet ID tidak dijumpai.")
            sys.exit(1)
    else:
        print(f"✓ Subnet OCID: {subnet_id[:20]}...")

    image_id = find_ubuntu_amd_image(compute_client, compartment_id)
    if not image_id:
        print("❌ [RALAT KRITIKAL]: Image ID Ubuntu AMD tidak dijumpai.")
        sys.exit(1)

    print("\n" + "=" * 60)
    print(" MENJALANKAN TEMBAKAN PERMOHONAN SLOT VM AMD ALWAYS FREE")
    print(" Target Shape : VM.Standard.E2.1.Micro (AMD EPYC)")
    print(" Specs        : 1/8 OCPU, 1 GB RAM (Fixed Shape)")
    print(f" Region       : {config['region']}")
    print("=" * 60 + "\n")

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
        )
    )

    try:
        response = compute_client.launch_instance(instance_details)
        print(f"🎉 [BERJAYA!] VM AMD Micro berjaya dicipta!")
        print(f"Instance ID: {response.data.id}")
    except oci.exceptions.ServiceError as e:
        if e.status == 500 or "OutOfCapacity" in str(e):
            print(f"⚠️  [FULL SLOT] Kapasiti penuh di {ad_name}. Status: {e.status} - {e.code}")
        elif e.status == 400 and "LimitExceeded" in str(e):
            print(f"⚠️  [LIMIT EXCEEDED] Anda telah mencapai had kuota 2 unit VM AMD Always Free.")
        else:
            print(f"❌ [RALAT PERMOHONAN OCI]: Status {e.status} - {e.code}: {e.message}")
    except Exception as e:
        print(f"❌ [RALAT SISTEM UNKNOWN]: {e}")


if __name__ == "__main__":
    run_sniper()
