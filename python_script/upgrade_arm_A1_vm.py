import os, sys, oci

# Autentikasi OCI SDK
config = oci.config.from_file(os.getenv("OCI_KEY_FILE"))
compute_client = oci.core.ComputeClient(config)
compartment_id = os.getenv("OCI_COMPARTMENT_ID") or config["tenancy"]

# 1. Cari VM ARM yang sedang berjalan
instances = compute_client.list_instances(compartment_id=compartment_id).data
arm_vms = [i for i in instances if i.shape == "VM.Standard.A1.Flex" and i.lifecycle_state == "RUNNING"]

if not arm_vms:
    print("❌ Tiada VM ARM aktif dijumpai untuk dinaik taraf.")
    sys.exit(0)

target_vm = arm_vms[0]

# 2. Hantar permintaan API untuk upgrade ke 2 OCPU / 12 GB RAM
update_details = oci.core.models.UpdateInstanceDetails(
    shape_config=oci.core.models.UpdateInstanceShapeConfigDetails(
        ocpus=2.0,
        memory_in_gbs=12.0
    )
)

try:
    print(f"🚀 Mencuba upgrade VM '{target_vm.display_name}' ke 2 OCPU / 12 GB RAM...")
    compute_client.update_instance(target_vm.id, update_details)
    print("🎉 BERJAYA! VM telah dinaikkan spesifikasi secara automatik!")
except oci.exceptions.ServiceError as e:
    print(f"⚠️ Kapasiti penuh: {e.message}")