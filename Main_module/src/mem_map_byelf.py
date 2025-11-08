from elftools.elf.elffile import ELFFile
import re
import os
import datetime


from pathlib import Path

base_dir = Path(__file__).resolve().parent.parent  # go up from src/
elf_file_path = base_dir / "data" / "elf" / "XCP_slave_disco.elf"


if not os.path.exists(elf_file_path):
    print(f"ELF file '{elf_file_path}' not found.")
    exit(1)


# Patterns for library-related / non-user-defined variables
EXCLUDE_PATTERNS = [
    r'^RCC_.*', r'^GPIO_.*', r'^hspi$', r'^tickstart$', r'^status$', r'^pllvco$',
    r'^pllp$', r'^pllsource$', r'^pllm$', r'^pid$', r'^length$', r'^addr$',
    r'^wait$', r'^prevTickFreq$', r'^prioritygroup$', r'^reg_value$',
    r'^stream_number$', r'^flagBitshiftOffset$', r'^timeout$', r'^regs$',
    r'^mask_cpltlevel$', r'^odr$', r'^bitstatus$', r'^position$', r'^ioposition$',
    r'^iocurrent$', r'^sysclockfreq$', r'^pll_config$', r'^pwrclkchanged$',
    r'^itsource$', r'^itflag$', r'^errorcode$', r'^abortcplt$', r'^txallowed$',
    r'^initial_TxXferCount$', r'^tmp_.*'
]

def is_user_defined_variable(name):
    """Check if the variable name is likely user-defined."""
    for pattern in EXCLUDE_PATTERNS:
        if re.match(pattern, name):
            return False
    return True

def get_memory_address(location):
    """Parse DWARF location expression to extract memory address in little-endian format."""
    try:
        if location[0] == 3:  # DW_OP_addr
            addr_bytes = location[1:5]  # Assuming 4-byte address
            # Little-endian: least significant byte first, no reversal
            address = sum(b << (i * 8) for i, b in enumerate(addr_bytes))
            return f"0x{address:08x}"
        return str(location)
    except:
        return str(location)

def get_array_details(dwarfinfo, type_ref_offset):
    """Manually resolve array details by traversing DIEs."""
    try:
        for cu in dwarfinfo.iter_CUs():
            for die in cu.iter_DIEs():
                if die.offset == type_ref_offset:
                    # Follow typedefs, pointers, or const types
                    while die.tag in ["DW_TAG_typedef", "DW_TAG_pointer_type", "DW_TAG_const_type"]:
                        if "DW_AT_type" in die.attributes:
                            type_ref_offset = die.attributes["DW_AT_type"].raw_value
                            for cu2 in dwarfinfo.iter_CUs():
                                for next_die in cu2.iter_DIEs():
                                    if next_die.offset == type_ref_offset:
                                        die = next_die
                                        break
                                else:
                                    continue
                                break
                        else:
                            break
                    if die.tag != "DW_TAG_array_type":
                        return None, None
                    # Get element count
                    element_count = None
                    for child in die.iter_children():
                        if child.tag == "DW_TAG_subrange_type":
                            if "DW_AT_count" in child.attributes:
                                element_count = child.attributes["DW_AT_count"].value
                            elif "DW_AT_upper_bound" in child.attributes:
                                element_count = child.attributes["DW_AT_upper_bound"].value + 1
                            break
                    # Get base type
                    base_type = None
                    if "DW_AT_type" in die.attributes:
                        base_type_offset = die.attributes["DW_AT_type"].raw_value
                        for cu2 in dwarfinfo.iter_CUs():
                            for base_die in cu2.iter_DIEs():
                                if base_die.offset == base_type_offset:
                                    base_type = base_die.attributes.get("DW_AT_name", None)
                                    base_type = base_type.value.decode() if base_type else "Unknown"
                                    break
                    return element_count, base_type
        return None, None
    except:
        return None, None



elf_basename = os.path.splitext(os.path.basename(elf_file_path))[0]
timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
output_dir = base_dir / "data" / "csv"
output_dir.mkdir(parents=True, exist_ok=True)
output_csv = os.path.join(output_dir, f"{elf_basename}_{timestamp}.csv")


user_defined_vars = []
try:
    with open(output_csv, "w") as csv_file:
        csv_file.write("Variable,Address,No of Elements,Type\n")
        elf = ELFFile(open(elf_file_path, "rb"))
        if not elf.has_dwarf_info():
            print("No DWARF info found in the ELF file.")
            exit(1)

        dwarfinfo = elf.get_dwarf_info()
        variable_found = False

        for CU in dwarfinfo.iter_CUs():
            for DIE in CU.iter_DIEs():
                if DIE.tag == "DW_TAG_variable":
                    name = DIE.attributes.get("DW_AT_name")
                    loc = DIE.attributes.get("DW_AT_location")
                    vartype = DIE.attributes.get("DW_AT_type")
                    if name and loc:
                        variable_name = name.value.decode()
                        address = get_memory_address(loc.value)
                        if address.startswith("[145,"):
                            continue
                        if is_user_defined_variable(variable_name):
                            variable_found = True
                            elements, var_type = (None, None)
                            if vartype:
                                elements, var_type = get_array_details(dwarfinfo, vartype.raw_value)
                            if elements is not None and var_type is not None:
                                pass
                            else:
                                elements = 1
                                var_type = "Uint32_t"
                            csv_line = f"{variable_name},{address},{elements},{var_type}"
                            user_defined_vars.append(csv_line)
                            csv_file.write(f"{csv_line}\n")

        if not variable_found:
            print("No user-defined variables found.")

    if os.path.exists(output_csv) and os.path.getsize(output_csv) > 0:
        print("User defines:")
        for var in user_defined_vars:
            print(var)
    else:
        print(f"{output_csv} is empty or was not created.")

except Exception:
    pass  
