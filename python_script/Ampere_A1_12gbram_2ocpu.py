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
    print("❌ [RALAT KRITIKAL] Pustaka 'oci' belum dipasang.")
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
    except Exception:
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
    print("=" * 65)
    print(" 🔍 MENYEMAK KUNCI GPG & AUTENTIKASI OCI (ARM AMPERE A1)")
    print("=" * 65)

    tenancy = get_env_var(["OCI_TENANCY", "TENANCY", "tenancy"])
    user = get_env_var(["OCI_USER", "USER", "user"])
    fingerprint = get_env_var(["OCI_FINGERPRINT", "FINGERPRINT", "fingerprint"])
    region = get_env_var(["OCI_REGION", "REGION", "region"], "ap-singapore-1")
    compartment_id = get_env_var(["OCI_COMPARTMENT_ID", "COMPARTMENT_ID"]) or tenancy
    subnet_id = get_env_var(["OCI_SUBNET_ID", "SUBNET_ID"])
    key_file_env = get_env_var(["OCI_KEY_FILE", "KEY_FILE"])
    gpg_passphrase = get_env_var(["GPG_PASSPHRASE", "OCI_KEY_PASSPHRASE", "PASSPHRASE"])

    key_file_path = None
    ssh_public_key = None

    # 1. Semakan API Private Key (.pem)
    if key_file_env and os.path.exists(key_file_env):
        key_file_path = key_file_env
        print(f"🔑 API Private Key dibaca dari fail: {key_file_path}")
    elif gpg_passphrase:
        api_gpg = "python_script/braderdin007@gmail.com-2026-07-26T17_31_09.593Z.pem.gpg"
        pem_content = decrypt_gpg(api_gpg, gpg_passphrase)
        if pem_content:
            tmp_key = tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.pem')
            tmp_key.write(pem_content)
            tmp_key.close()
            key_file_path = tmp_key.name
            print("🔑 API Private Key (.pem.gpg) berjaya dinyahsulit.")

    if not key_file_path:
        print("❌ [RALAT KRITIKAL] API Private Key gagal dijumpai atau dinyahsulit!")
        sys.exit(1)

    # 2. Semakan SSH Public Key (.pub)
    if gpg_passphrase:
        ssh_pub_gpg = "python_script/ssh-key-2026-07-27.key.pub.gpg"
        ssh_public_key = decrypt_gpg(ssh_pub_gpg, gpg_passphrase)

    if not ssh_public_key and os.path.exists("python_script/ssh-key-2026-07-27.key.pub"):
        with open("python_script/ssh-key-2026-07-27.key.pub", "r") as f:
            ssh_public_key = f.read().strip()

    if ssh_public_key:
        print("🔐 SSH Public Key sedia disuntik ke VM.")
    else:
        print("⚠️ SSH Public Key tiada. VM akan dicipta tanpa akses kunci SSH.")

    print(f"🌐 Tenancy OCID       : {tenancy[:15]}...{tenancy[-5:] if tenancy else ''}")
    print(f"👤 User OCID          : {user[:15]}...{user[-5:] if user else ''}")
    print(f"🖐️ Fingerprint        : {fingerprint}")
    print(f"📍 Region             : {region}")

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
    print("⚠️ [AMARAN] OCI_SUBNET_ID tiada. Mencari Subnet VCN secara automatik...")
    try:
        vcns = network_client.list_vcns(compartment_id=compartment_id).data
        if vcns:
            subnets = network_client.list_subnets(compartment_id=compartment_id, vcn_id=vcns[0].id).data
            if subnets:
                print(f"🌐 Subnet dijumpai: {subnets[0].id}")
                return subnets[0].id
    except Exception as e:
        print(f"❌ [RALAT AUTO SUBNET]: {e}")
    return None


def find_ubuntu_arm_image(compute_client, compartment_id):
    try:
        images = compute_client.list_images(
            compartment_id=compartment_id,
            operating_system="Canonical Ubuntu",
            shape="VM.Standard.A1.Flex",
            sort_by="TIMECREATED",
            sort_order="DESC"
        ).data

        for img in images:
            name_lower = img.display_name.lower()
            if "24.04" in name_lower and "minimal" not in name_lower:
                return img.id, img.display_name

        for img in images:
            name_lower = img.display_name.lower()
            if "22.04" in name_lower and "minimal" not in name_lower:
                return img.id, img.display_name

        if images:
            return images[0].id, images[0].display_name
    except Exception as e:
        print(f"❌ [RALAT CARI IMAGE]: {e}")
    return None, None


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
        print("✅ Autentikasi Kunci OCI SDK: BERJAYA")
    except Exception as e:
        print(f"❌ [RALAT AUTENTIKASI OCI SDK]: {e}")
        sys.exit(1)

    try:
        ads = identity_client.list_availability_domains(compartment_id=config['tenancy']).data
    except Exception as e:
        print(f"❌ [RALAT GET AD]: {e}")
        sys.exit(1)

    if not subnet_id:
        subnet_id = find_default_subnet(network_client, compartment_id)
        if not subnet_id:
            print("❌ [RALAT SUBNET]: Subnet ID tidak dijumpai.")
            sys.exit(1)

    image_id, image_name = find_ubuntu_arm_image(compute_client, compartment_id)
    if not image_id:
        print("❌ [RALAT IMAGE]: Tiada Image Ubuntu ARM dijumpai.")
        sys.exit(1)

    shape = "VM.Standard.A1.Flex"
    ocpus = 1.0
    memory_in_gbs = 9.0
    boot_volume_size_gbs = 100

    print("\n" + "=" * 65)
    print(" 🚀 MENJALANKAN TEMBAKAN PERMOHONAN SLOT VM ARM ALWAYS FREE")
    print("=" * 65)
    print(f" 🖥️  Target Shape  : {shape} (Ampere A1)")
    print(f" 🧠 Processor     : {ocpus} OCPU")
    print(f" ⚡ Memory (RAM)  : {memory_in_gbs} GB")
    print(f" 💾 Boot Storage  : {boot_volume_size_gbs} GB")
    print(f" 🐧 OS Image      : {image_name}")
    print(f" 🌐 Region        : {config['region']}")
    print("=" * 65 + "\n")

    metadata = {}
    if ssh_public_key:
        metadata["ssh_authorized_keys"] = ssh_public_key

    for ad in ads:
        ad_name = ad.name
        print(f"🎯 [MENCUBA SLOT] AD Domain: {ad_name}")

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
            print(f" 🎉 [BERJAYA!] VM ARM Ampere A1 berjaya dicipta!")
            print(f" 🆔 Instance ID: {response.data.id}")
            print("🎉" * 20)
            sys.exit(0)
        except oci.exceptions.ServiceError as se:
            if se.status == 500 or "OutOfCapacity" in se.code or "Out of host capacity" in str(se.message):
                print(f"⚠️  [FULL SLOT] Kapasiti penuh di {ad_name}. Status: {se.status} - {se.code}")
            elif se.status == 429:
                print(f"⚠️  [RATE LIMIT] Terlalu banyak permintaan (Too Many Requests). Status: 429")
            elif se.status == 400 and "LimitExceeded" in str(se):
                print(f"⚠️  [LIMIT EXCEEDED] Had kuota ARM Always Free telah dicapai.")
            else:
                print(f"❌ [RALAT SERVIS OCI ({se.status})]: Code: {se.code} | Message: {se.message}")
        except Exception as ex:
            print(f"❌ [RALAT TIDAK DIJANGKA]: {str(ex)}")


if __name__ == "__main__":
    run_sniper()