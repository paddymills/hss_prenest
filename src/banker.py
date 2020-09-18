
import xlwings
import re

import geometry

NUM_FRAC = re.compile(r'(\d+)?\s*(\d+/\d+)?"')
GRADE = re.compile(r"ASTM\s*(A\d+)-\w*.?\s*(\d+)\s*\w*")


def main():
    wb = xlwings.books.active
    s = wb.sheets["1200131D-7"]

    job, shipment = s.name.split("-")
    parts = dict()

    i = 4
    while 1:
        # increment at beginning so we can use the `continue` statement
        i += 1

        row = s.range((i, 1), (i, 11)).value
        for _i, x in enumerate(row):
            if x and type(x) is str:
                row[_i] = x.strip()

        if not any(row):
            break

        if process(row):
            part = parse_row(row)

            if part["part"] in parts.keys():
                in_dict = parts[part["part"]]
                test_keys = ("thk", "wid", "len", "grade")

                if all([part[k] == in_dict[k] for k in test_keys]):
                    parts[part["part"]]["qty"] += part["qty"]
                    continue
                else:
                    part["part"] = get_next_part_name(parts, part["part"])

            parts[part["part"]] = part

    for p in parts.values():
        p["part"] = f"{job}-{shipment}_{p['part']}"
        p["WO"] = f"PN_{job}-{shipment}"
        geo = geometry.Part(prenest=True, **p)
        geo.generate_xml()
        print(p)


def parse_row(row):
    mm = str(int(row[1])).zfill(5)
    qty = row[2]
    thk, wid = map(handle_dim, row[4].split("X"))
    length = handle_len(row[5])
    grade = '-'.join(GRADE.match(row[6]).groups()) + "T2"
    part = row[9]

    return dict(
        mm=mm,
        qty=qty,
        thk=thk,
        wid=wid,
        len=length,
        grade=grade,
        part=part,
    )


def handle_dim(dim):
    integer, fraction = NUM_FRAC.match(dim).groups()

    value = 0.0
    if integer:
        value += float(integer)
    if fraction:
        num, denom = fraction.split('/')
        value += int(num) / int(denom)

    return value


def handle_len(length):
    feet, inches = length.split("'-")

    return int(feet) * 12 + handle_dim(inches)


def process(row):
    if not row[1]:
        return False
    if row[3] not in ("PL", "FB"):
        return False
    if str(row[1])[0] in ("3", "4"):
        return False

    return True


def get_next_part_name(parts_dict, name):
    suffixes = 'abcdefghijklmnopqrstuvwxyz'
    for suffix in suffixes:
        if name + suffix not in parts_dict.keys():
            return name + suffix


if __name__ == "__main__":
    main()
