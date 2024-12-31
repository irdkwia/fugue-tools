import argparse
import os

parser = argparse.ArgumentParser(description="Keitai Fugue Mixed NAND Extractor")
parser.add_argument("primary")
parser.add_argument("secondary", nargs="?")
parser.add_argument("output")
parser.add_argument(
    "-i",
    "--ignore",
    help="Ignore asserts.",
    action=argparse.BooleanOptionalAction,
)
parser.add_argument(
    "-c",
    "--autocorrect",
    help="Tries to autocorrect.",
    action=argparse.BooleanOptionalAction,
)

LEN_TABLE = 166

args = parser.parse_args()

table = {}

OFFSET = [0x100, 0x7F300] if args.secondary else [0, 0x100000000]

with open(args.primary, "rb") as nanda:
    with open(args.secondary if args.secondary else args.primary, "rb") as nandb:
        path_ooba = os.path.join(
            os.path.dirname(args.primary),
            f"{os.path.splitext(os.path.basename(args.primary))[0]}.oob",
        )
        if args.secondary:
            path_oobb = os.path.join(
                os.path.dirname(args.secondary),
                f"{os.path.splitext(os.path.basename(args.secondary))[0]}.oob",
            )
        else:
            path_oobb = path_ooba
        with open(path_ooba, "rb") as ooba:
            with open(path_oobb, "rb") as oobb:
                nands = [nanda, nandb]
                oobs = [ooba, oobb]
                for idx, oob in enumerate(oobs):
                    nand = nands[idx]
                    oob.seek(OFFSET[0] * 0x10)
                    spare = oob.read(0x10)
                    block_number = 0
                    while len(spare) > 0 and block_number < OFFSET[1]:
                        objid = int.from_bytes(spare[2:5], "big")
                        if objid & 0x700000 == 0x700000 and spare[0:2] == b"\xFF\xFF":
                            objid = objid & 0x0FFFFF
                            if objid == 0x419:  # Main table ID
                                nand.seek((OFFSET[0] + block_number) * 0x200)
                                data = nand.read(0x200)
                                generation = int.from_bytes(data[4:8], "big")
                                chunk_id = int.from_bytes(data[8:10], "big")
                                g = table.get(chunk_id, [b"", 0x100000000])
                                if g[1] >= generation:
                                    g[1] = generation
                                    tbl = data[0xE:]
                                    g[0] = [
                                        int.from_bytes(tbl[i : i + 3], "big")
                                        for i in range(0, len(tbl), 3)
                                    ]
                                table[chunk_id] = g
                        block_number += 1
                        spare = oob.read(0x10)
                with open(args.output, "wb") as file:
                    for k, v in sorted(table.items()):
                        file.seek(k * LEN_TABLE * 0x200)
                        a = k * LEN_TABLE
                        for x in v[0]:
                            if x == 0xFFFFFF:
                                file.write(bytes(0x200))
                            else:
                                if x >= OFFSET[1]:
                                    idx = 1
                                    nands[idx].seek((x - OFFSET[1] + OFFSET[0]) * 0x200)
                                    oobs[idx].seek((x - OFFSET[1] + OFFSET[0]) * 0x10)
                                else:
                                    idx = 0
                                    nands[idx].seek((x + OFFSET[0]) * 0x200)
                                    oobs[idx].seek((x + OFFSET[0]) * 0x10)
                                data = nands[idx].read(0x200)
                                spare = oobs[idx].read(0x10)
                                objid = int.from_bytes(spare[2:5], "big")
                                try:
                                    assert (
                                        objid & 0x700000 == 0
                                        and spare[0:2] == b"\xFF\xFF"
                                        and objid & 0x0FFFFF == a
                                    ), (
                                        "Spare ID %06X does not match position in file [%06X] (FUGUE table %04X wants block %06X)"
                                        % (objid, a, k, x)
                                    )
                                except Exception as e:
                                    if len(data) < 0x200:
                                        data += bytes(0x200 - len(data))
                                    if args.autocorrect:
                                        auto = None
                                        fail = 1
                                        for h in range(2 if args.secondary else 1):
                                            oobs[h].seek(0)
                                            nspare = oobs[h].read(0x10)
                                            block_number = 0
                                            while len(nspare) > 0:
                                                nobjid = int.from_bytes(
                                                    nspare[2:5], "big"
                                                )
                                                if (
                                                    nobjid & 0x700000 == 0
                                                    and nspare[0:2] == b"\xFF\xFF"
                                                    and nobjid & 0x0FFFFF == a
                                                ):
                                                    if auto is None:
                                                        auto = [h, block_number]
                                                        fail = 0
                                                    else:
                                                        fail = 2
                                                nspare = oobs[idx].read(0x10)
                                                block_number += 1
                                        if fail == 0:
                                            noffset = auto[1] - OFFSET[0]
                                            if auto[0] == 1:
                                                noffset += OFFSET[1]
                                            print(
                                                str(e)
                                                + " -> "
                                                + ("Corrected to %06X" % noffset)
                                            )
                                            nands[auto[0]].seek(auto[1] * 0x200)
                                            data = nands[auto[0]].read(0x200)
                                        elif fail == 1:
                                            print(
                                                str(e)
                                                + " -> Correcting failed: no suitable block found."
                                            )
                                        elif fail == 2:
                                            print(
                                                str(e)
                                                + " -> Correcting failed: multiple suitable blocks found."
                                            )
                                    elif args.ignore:
                                        print(e)
                                    else:
                                        raise e
                                file.write(data)
                            a += 1
