import os
import sys
import oci
from dotenv import load_dotenv

load_dotenv('.env.local')

print("============================================================")
print(" MENYEMAK KUNCI & AUTENTIKASI OCI (AMD MICRO)")
print("============================================================")

tenancy = os.getenv("OCI_TENANCY")
user = os.getenv("OCI_USER")
fingerprint = os.getenv("OCI_FINGERPRINT")
region = os.getenv("OCI_REGION")
key_content = os.getenv("OCI_KEY_CONTENT")
subnet_id = os.getenv("OCI_SUBNET_ID")
compartment_id = os.getenv("OCI_COMPARTMENT_ID") or tenancy

missing_keys = []
if not tenancy: missing_keys.append("OCI_TENANCY")
if not user: missing_keys.append("OCI_USER")
if not fingerprint: missing_keys.append("OCI_FINGERPRINT")
if not region: missing_keys.append("OCI_REGION")
if not key_content: missing_keys.append("OCI_KEY_CONTENT")

if missing_keys:
    print(f"❌ [RALAT KUNCI]: Kunci berikut TIADA dalam .env.local / GitHub Secrets:")
    for k in missing_keys:
        print(f"   - {k}")
    sys.exit(1)

key_str = key_content.strip('"\'').replace("\\n", "\n")

config = {
    "user": user,
    "key_content": key_str,
    "fingerprint": fingerprint,
    "tenancy": tenancy,
    "region": region
}

try:
    # Memvalidasi konfigurasi OCI SDK
    oci.config.validate_config(config)
    identity_client = oci.identity.IdentityClient(config)
    compute_client = oci.core.ComputeClient(config)
    network_client = oci.core.VirtualNetworkClient(config)
    print("✓ Autentikasi Kunci OCI SDK: BERJAYA")
except Exception as e:
    print(f"❌ [RALAT AUTENTIKASI OCI SDK]: {e}")
    sys.exit(1)

try:
    ads = identity_client.list_availability_domains(compartment_id=tenancy).data
    ad_name = ads[0].name
    print(f"✓ Availability Domain: {ad_name}")
except Exception as e:
    print(f"❌ [RALAT GET AD]: {e}")
    sys.exit(1)

if not subnet_id:
    print("⚠️  [AMARAN] OCI_SUBNET_ID tiada. Mencari Subnet VCN secara automatik...")
    try:
        vcns = network_client.list_vcns(compartment_id=compartment_id).data
        if vcns:
            subnets = network_client.list_subnets(compartment_id=compartment_id, vcn_id=vcns[0].id).data
            if subnets:
                subnet_id = subnets[0].id
                print(f"✓ Subnet dijumpai: {subnet_id}")
            else:
                print("❌ [RALAT SUBNET]: VCN wujud tetapi tiada Subnet di dalamnya.")
                sys.exit(1)
        else:
            print("❌ [RALAT VCN]: Tiada VCN dijumpai dalam akaun ini.")
            sys.exit(1)
    except Exception as e:
        print(f"❌ [RALAT AUTO SUBNET]: {e}")
        sys.exit(1)
else:
    print(f"✓ Subnet OCID: {subnet_id[:20]}...")

try:
    images = compute_client.list_images(
        compartment_id=compartment_id,
        operating_system="Canonical Ubuntu",
        shape="VM.Standard.E2.1.Micro",
        sort_by="TIMECREATED",
        sort_order="DESC"
    ).data
    
    if not images:
        print("❌ [RALAT IMAGE]: Tiada Image Ubuntu (x86_64) dijumpai untuk AMD Micro.")
        sys.exit(1)
        
    image_id = images[0].id
    print(f"✓ Image Ubuntu AMD: {images[0].display_name}")
except Exception as e:
    print(f"❌ [RALAT CARI IMAGE]: {e}")
    sys.exit(1)

print("\n============================================================")
print(" MENJALANKAN TEMBAKAN PERMOHONAN SLOT VM AMD ALWAYS FREE")
print(" Target Shape : VM.Standard.E2.1.Micro (AMD EPYC)")
print(" Specs        : 1/8 OCPU, 1 GB RAM (Fixed Shape)")
print(f" Region       : {region}")
print("============================================================\n")

instance_details = oci.core.models.LaunchInstanceDetails(
    compartment_id=compartment_id,
    availability_domain=ad_name,
    display_name="AlwaysFree-AMD-Micro",
    shape="VM.Standard.E2.1.Micro",
    image_id=image_id,
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
