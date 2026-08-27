# -*- coding: utf-8 -*-
"""
OCI ARM Slot Sniper - Always Free (2 OCPU / 12GB RAM / 200GB Boot Volume / Ubuntu)
Direka untuk berjalan di Local (.env.local) dan GitHub Actions (GitHub Secrets).
"""

import os
import sys
import tempfile
import traceback

# Support loading .env.local for local testing
try:
    from dotenv import load_dotenv
    # Prioritise .env.local if present, else fallback to .env
    if os.path.exists(".env.local"):
        load_dotenv(".env.local", override=True)
        print("[INFO] Berjaya memuatkan tetapan daripada file .env.local")
    elif os.path.exists(".env"):
        load_dotenv(".env", override=True)
        print("[INFO] Memuatkan tetapan daripada file .env")
    else:
        print("[INFO] Tiada file .env.local/.env dijumpai. Membaca daripada Environment Variables / GitHub Secrets.")
except ImportError:
    print("[WARN] Modul 'python-dotenv' tidak dipasang. Membaca pembolehubah persekitaran terus daripada sistem/GitHub Secrets.")

try:
    import oci
except ImportError:
    print("[RALAT KRITIKAL] Pustaka 'oci' belum dipasang. Sila jalankan: pip install -r requirements.txt")
    sys.exit(1)


def get_env_var(keys, default=None):
    """Membaca kunci persekitaran mengikut pelbagai variasi nama."""
    if isinstance(keys, str):
        keys = [keys]
    for key in keys:
        val = os.getenv(key)
        if val and val.strip():
            return val.strip()
    return default


def validate_config():
    """Menyemak dan memvalidasi semua kunci OCI yang diperlukan."""
    print("=" * 60)
    print(" MENYEMAK KUNCI & SPESIFIKASI CONFIGURATION OCI")
    print("=" * 60)

    errors = []
    
    tenancy = get_env_var(["OCI_TENANCY", "TENANCY", "tenancy"])
    user = get_env_var(["OCI_USER", "USER", "user"])
    fingerprint = get_env_var(["OCI_FINGERPRINT", "FINGERPRINT", "fingerprint"])
    region = get_env_var(["OCI_REGION", "REGION", "region"], "ap-singapore-1")
    key_content = get_env_var(["OCI_KEY_CONTENT", "OCI_PRIVATE_KEY", "KEY_CONTENT"])
    key_file = get_env_var(["OCI_KEY_FILE", "KEY_FILE", "key_file"])
    compartment_id = get_env_var(["OCI_COMPARTMENT_ID", "COMPARTMENT_ID", "Stack_OCID"]) or tenancy
    subnet_id = get_env_var(["OCI_SUBNET_ID", "SUBNET_ID", "subnet_id"])
    ssh_public_key = get_env_var(["OCI_SSH_PUBLIC_KEY", "SSH_PUBLIC_KEY"])

    # Semakan kunci wajib
    if not tenancy:
        errors.append("❌ OCI_TENANCY tiada! Tambah OCI_TENANCY=ocid1.tenancy.oc1... dalam .env.local atau GitHub Secrets.")
    else:
        print(f"✓ Tenancy OCID       : {tenancy[:15]}...{tenancy[-5:]}")

    if not user:
        errors.append("❌ OCI_USER tiada! Tambah OCI_USER=ocid1.user.oc1... dalam .env.local atau GitHub Secrets.")
    else:
        print(f"✓ User OCID          : {user[:15]}...{user[-5:]}")

    if not fingerprint:
        errors.append("❌ OCI_FINGERPRINT tiada! Tambah OCI_FINGERPRINT=xx:xx:... dalam .env.local atau GitHub Secrets.")
    else:
        print(f"✓ Fingerprint        : {fingerprint}")

    if not region:
        errors.append("❌ OCI_REGION tiada! Tambah OCI_REGION=ap-singapore-1 dalam .env.local atau GitHub Secrets.")
    else:
        print(f"✓ Region             : {region}")

    if not key_content and not key_file:
        errors.append("❌ OCI_KEY_CONTENT / OCI_KEY_FILE tiada! Sila letakkan kandungan Private Key (.pem) ke OCI_KEY_CONTENT.")
    else:
        print(f"✓ Private Key Status : Wujud ({'Key Content String' if key_content else 'File Path: ' + key_file})")

    if not subnet_id:
        print("⚠️  [AMARAN] OCI_SUBNET_ID tiada. Skrip akan cuba mencarinya secara automatik dari VCN percuma.")
    else:
        print(f"✓ Subnet OCID        : {subnet_id[:15]}...{subnet_id[-5:]}")

    if errors:
        print("\n" + "=" * 60)
        print(" SENARAI RALAT KUNCI / CONFIGURATION MISSING:")
        print("=" * 60)
        for err in errors:
            print(err)
        print("=" * 60)
        print("Sila lengkapkan kunci di atas dalam .env.local (untuk local) atau GitHub Secrets (untuk GitHub Actions) sebelum mencuba semula.\n")
        return None

    # Bina oci config dictionary
    config = {
        "user": user,
        "fingerprint": fingerprint,
        "tenancy": tenancy,
        "region": region,
    }

    # Urus Private Key (Key content vs Key file path)
    if key_content:
        # Bersihkan pembungkus quote jika ada
        key_str = key_content.strip('"\'').replace("\\n", "\n")
        # Simpan ke fail temporary jika menggunakan OCI SDK lama atau pass terus key_content jika disokong
        try:
            config["key_content"] = key_str
        except Exception:
            tmp_key = tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.pem')
            tmp_key.write(key_str)
            tmp_key.close()
            config["key_file"] = tmp_key.name
    elif key_file:
        config["key_file"] = key_file

    return {
        "config": config,
        "compartment_id": compartment_id,
        "subnet_id": subnet_id,
        "ssh_public_key": ssh_public_key
    }


def find_ubuntu_arm_image(compute_client, compartment_id):
    """Mencari Image ID Ubuntu terkini untuk seni bina ARM (aarch64)."""
    print("[INFO] Mencari Image Ubuntu ARM (aarch64) dalam compartment...")
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
                print(f"[SUCCESS] Dijumpai Image Ubuntu ARM: {img.display_name} ({img.id})")
                return img.id
        
        # Fallback to general list if specific shape filter returns empty
        if images:
            print(f"[INFO] Menggunakan Image Ubuntu terkini: {images[0].display_name} ({images[0].id})")
            return images[0].id

    except Exception as e:
        print(f"[RALAT] Gagal mendapatkan senarai image Ubuntu: {str(e)}")
    
    return None


def find_default_subnet(network_client, compartment_id):
    """Mencari Subnet ID secara automatik dari VCN yang sedia ada."""
    print("[INFO] Mencari Subnet sedia ada secara automatik...")
    try:
        subnets = network_client.list_subnets(compartment_id=compartment_id).data
        if subnets:
            selected_subnet = subnets[0].id
            print(f"[SUCCESS] Subnet dijumpai: {subnets[0].display_name} ({selected_subnet})")
            return selected_subnet
    except Exception as e:
        print(f"[RALAT] Gagal mencari Subnet: {str(e)}")
    return None


def run_sniper():
    """Fungsi Utama Percubaan Memohon Slot ARM Always Free (2 OCPU / 12GB RAM / 200GB Boot Volume)."""
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
        print("Sila pastikan OCI_USER, OCI_TENANCY, OCI_FINGERPRINT dan OCI_KEY_CONTENT adalah betul.")
        sys.exit(1)

    # 1. Dapatkan Availability Domains
    print("[INFO] Meminta senarai Availability Domains (AD)...")
    try:
        ads = identity_client.list_availability_domains(compartment_id=config['tenancy']).data
    except Exception as e:
        print(f"❌ [RALAT GET AD]: {str(e)}")
        sys.exit(1)

    if not ads:
        print("❌ [RALAT]: Tiada Availability Domain dijumpai bagi rantau ini.")
        sys.exit(1)

    # 2. dapatkan Subnet ID jika tiada dalam env
    if not subnet_id:
        subnet_id = find_default_subnet(network_client, compartment_id)
        if not subnet_id:
            print("❌ [RALAT KRITIKAL]: Subnet ID diperlukan untuk erschaffen Compute Instance. Tetapkan OCI_SUBNET_ID.")
            sys.exit(1)

    # 3. Dapatkan Image ID Ubuntu ARM
    image_id = find_ubuntu_arm_image(compute_client, compartment_id)
    if not image_id:
        print("❌ [RALAT KRITIKAL]: Image ID Ubuntu ARM tidak dijumpai.")
        sys.exit(1)

    # Spesifikasi Always Free yang diminta:
    # - Shape: VM.Standard.A1.Flex
    # - OCPU: 2
    # - RAM: 12 GB
    # - Storage: 200 GB
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
    print(f" Region         : {config.get('region')}")
    print("=" * 60)

    # Cubaan di setiap AD
    instance_created = False
    for ad in ads:
        ad_name = ad.name
        print(f"\n[TRY] Mencuba memohon slot di AD: {ad_name}...")

        # metadata SSH
        metadata = {}
        if ssh_public_key:
            metadata["ssh_authorized_keys"] = ssh_public_key

        launch_details = oci.core.models.LaunchInstanceDetails(
            display_name=f"OCI-ARM-2OCPU-12GB-Ubuntu",
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
                assign_public_ip=True,
                display_name="PrimaryVnic"
            ),
            metadata=metadata
        )

        try:
            response = compute_client.launch_instance(launch_details)
            instance = response.data
            print("🎉" * 20)
            print(" BERJAYA! SLOT VM ARM TELAH BERJAYA DIPEROLEHI!")
            print(f" Instance Name : {instance.display_name}")
            print(f" Instance OCID : {instance.id}")
            print(f" Lifecycle     : {instance.lifecycle_state}")
            print("🎉" * 20)
            instance_created = True
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

    if not instance_created:
        print("\n" + "-" * 60)
        print("ℹ️  Semua Availability Domain dipenuhi kapasiti buat masa ini.")
        print("Skrip ini perlu dijalankan secara berulang (Cron/Loop) sehingga slot dilepaskan.")
        print("-" * 60)


if __name__ == "__main__":
    run_sniper()
