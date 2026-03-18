try:
    import pdfplumber
except ImportError:
    pdfplumber = None


def _require_pdfplumber():
    if pdfplumber is None:
        raise ImportError("pdfplumber is required to parse ECD files.")

def ecd_parser_0(ecd_file):
    _require_pdfplumber()
    pdf = pdfplumber.open(ecd_file)
    page = pdf.pages[0] 
    raw_tables = page.extract_tables()
    table = [[x for x in row if x is not None] for row in raw_tables[0]]

    ecd = {}
    anchor = find_keyword_list2d(table, "ECD")
    if anchor:
        row, col = anchor
        row += 1
        ecd["ecd_no"] = table[row][0]
        ecd["project"] = table[row][1]
        ecd["change_class"] = table[row][2]
        ecd["cage_code"] = table[row][3]
        ecd["change_type"] = table[row][4]
        ecd["effectivity"] = table[row][5]
    else:
        raise ValueError("Can not found keyword")

    anchor = find_keyword_list2d(table, "ECD TITLE")
    if anchor:
        row, col = anchor
        row += 1
        ecd["ecd_title"] = table[row][0]
    else:
        raise ValueError("Can not found keyword")

    anchor = find_keyword_list2d(table, "Record of Change Revisions")
    if anchor:
        row, col = anchor
        row += 1
        if table[row][0] == "Originator":
            ecd["record_of_change"] = None
        else:
            ecd["record_of_change"] = table[row][0]
    else:
        raise ValueError("Can not found keyword")

    anchor = find_keyword_list2d(table, "Originator")
    if anchor:
        row, col = anchor
        row += 1
        ecd["originator"] = table[row][0]

        ecd["ata"] = table[row][1]
        if ecd["ata"] == "":
            ecd["ata"] = "00"

        ecd["subata"] = table[row][2]
        if ecd["subata"] == "":
            ecd["subata"] = "00"

        ecd["ecd_initiator"] = table[row][3]
        if ecd["ecd_initiator"]:
            ecd["ecd_initiator"] = ecd["ecd_initiator"].replace("\n", " ")

        ecd["status"] = table[row][4]
    else:
        raise ValueError("Can not found keyword")

    anchor = find_keyword_list2d(table, "Change Justification:")
    if anchor:
        row, col = anchor
        ecd["change_justification"] = table[row][2].replace("\n", " ")
        ecd["proposed_solution"] = table[row+1][1].replace("\n", " ")
        ecd["consequence"] = table[row+2][1].replace("\n", " ")
        ecd["impacted_groups"] = table[row+3][1].replace("\n", ", ")
    else:
        raise ValueError("Can not found keyword")

    return ecd

def ecd_parser_1(ecd_file):
    _require_pdfplumber()
    for i in range(2):
        try:
            pdf = pdfplumber.open(ecd_file)
            page = pdf.pages[i] 
            raw_tables = page.extract_tables()
            table = [[x for x in row if x is not None] for row in raw_tables[0]]

            ecd = {}
            ecd["project"] = table[4][1]
            ecd["change_class"] = table[4][2]
            ecd["change_type"] = str(table[4][3]).replace("\n", " ")
            ecd["effectivity"] = table[9][1]
            ecd["ecd_title"] = str(table[2][0]).replace("\n", " ")
            ecd["ecd_no"] = "-".join(str(table[4][0]).replace("\n", " ").split("-")[:2])
            ecd["record_of_change"] = table[7][0]
            ecd["requestor"] = table[11][1]
            ecd["originator"] = table[13][1]

            if "/" in str(table[14][1]):
                ecd["ata"] = str(table[14][1]).split("/")[0]
                ecd["subata"] = str(table[14][1]).split("/")[1]
            else:
                ecd["ata"] = ""
                ecd["subata"] = ""

            ecd["change_justification"] = table[15][1].replace("\n", " ")
            ecd["proposed_solution"] = table[16][1].replace("\n", " ")
            ecd["consequence"] = table[17][1].replace("\n", " ")
            ecd["impacted_groups"] = table[18][1].replace("\n", ", ")
            
            return ecd
        except IndexError as e:
            continue
    
    raise ValueError("Can not parse ECD")

def ecd_parser_2(ecd_file):
    _require_pdfplumber()
    for i in range(2):
        try:
            pdf = pdfplumber.open(ecd_file)
            page = pdf.pages[i] 
            raw_tables = page.extract_tables()
            table = [[x for x in row if x is not None] for row in raw_tables[0]]

            ecd = {}
            ecd["project"] = table[4][1]
            ecd["change_class"] = table[4][2]
            ecd["change_type"] = str(table[4][3]).replace("\n", " ")
            ecd["effectivity"] = table[9][1]
            ecd["ecd_title"] = str(table[2][0]).replace("\n", " ")
            ecd["ecd_no"] = str(table[4][0]).replace("\n", " ").split(ecd["ecd_title"])[0][:-1] 
            ecd["record_of_change"] = table[7][0]
            ecd["requestor"] = table[12][1]
            ecd["originator"] = table[14][1]

            if "/" in str(table[15][1]):
                ecd["ata"] = str(table[15][1]).split("/")[0]
                ecd["subata"] = str(table[15][1]).split("/")[1]
            else:
                ecd["ata"] = ""
                ecd["subata"] = ""

            ecd["change_justification"] = table[16][1].replace("\n", " ")
            ecd["proposed_solution"] = table[17][1].replace("\n", " ")
            ecd["consequence"] = table[18][1].replace("\n", " ")
            ecd["impacted_groups"] = table[19][1].replace("\n", ", ")
            
            return ecd
        except IndexError as e:
            continue
    
    raise ValueError("Can not parse ECD")
    
def safe_ecd_parse(ecd):
    try:
        result = ecd_parser_1(ecd)
        return result
    except ValueError as e:
        pass
    
    try:
        result = ecd_parser_2(ecd)
        return result
    except ValueError as e:
        pass
    
    raise ValueError(f"No parser can parse.")
