import os

DXL_OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "doors_dxl_output.log").replace("\\", "\\\\")

def get_ata_chapter_check(module_path):
    dxl_ata_chapter_check = r'''
Stream output = write("__doors_dxl_output__")

string refModuleName = "__module_path__"

Module m = read(refModuleName, false, true)
if (null m) {
	output << "Module not found: " refModuleName "\n"
	halt
}

Object o
string aplic
string ata

for o in m do {
    aplic = o.("Applicable or Not Applicable ")
    ata = o.("ATA Chapter")
    if (aplic == "Not Applicable" && ata != ""){
        output << o.("Para") "\n"
    }
}

close(output)
close(m)
'''
    dxl_ata_chapter_check = dxl_ata_chapter_check.replace("__doors_dxl_output__", DXL_OUTPUT_PATH)
    dxl_ata_chapter_check = dxl_ata_chapter_check.replace("__module_path__", module_path)
    return dxl_ata_chapter_check


def get_req_poc_linker(ref_module_name, link_module_name, target_module_name, ref_attr_poc, ref_attr_req, target_attr_poc, start_index, text_length, direction, activeness):
    req_poc_linker = r'''
Stream output = write("__doors_dxl_output__")

#include <addins/user/yck.dxl>

///// PART 1
string refModuleName = "__ref_module_name__"
Module refModule

if (__activeness__ && "__direction__" == "ref2tar"){
	refModule = edit(refModuleName, false, true, true)
 	if (!isEdit refModule){
		output << "The module cannot be opened in edit mode: " refModuleName "\n"
  		halt
    }
}else{
	refModule = read(refModuleName, false, true)
}

if (null refModule) {
    output << "Module not found: " refModuleName "\n"
	halt
}

string targetModuleName = "__target_module_name__"
Module targetModule

if (__activeness__ && "__direction__" == "tar2ref"){
	targetModule = edit(targetModuleName, false, true, true)
 	if (!isEdit targetModule){
		output << "The module cannot be opened in edit mode: " targetModuleName "\n"
  		halt
    }
}else{
	targetModule = read(targetModuleName, false, true)
}

if (null targetModule) {
    output << "Module not found: " targetModuleName "\n"
	halt
}

Object o
Skip root = create
int i
string docs, param
string reqColumnName = "__ref_attr_req__"
string panelName = "__ref_attr_poc__"
int cropSize = __start_index__
int textLength = __text_length__
int loopLimit = -1

i= 0
for o in refModule do {
	docs= o.(panelName)
	param= o.reqColumnName

	Skip list = createString
	Skip elementList = create
	Tokenize(docs, '\n', list)

	string tt
	for tt in list do{
		tt = stripstr(tt)
		tt =  substr(tt, cropSize, textLength)
		put(root, tt, (Skip create))

		find(root, tt, elementList)
		put(elementList, param, o)
		delete(root, tt)
		put(root, tt, elementList)
	}

	i++
	if (i == loopLimit) break
}

Skip skipElement
for skipElement in root do {
	output << "** "(stripstr(string key root)) " **\n"
	for o in skipElement do{
		output << o.reqColumnName "\n"
	}
	output << "\n"
}

///// PART 2

string linkModuleName = "__link_module_name__"

string targetSearchAttr = "__target_attr_poc__"

Object objElement
for skipElement in root do {
	o = FindObjectByAttribute(targetModule, targetSearchAttr, stripstr(string key root))
	if (null o) {
	    output << "Object not found on target module: " (stripstr(string key root)) "\n"
	}
	else {
		//output << o.("Object Heading") "\n"
		for objElement in skipElement do {
			if (__activeness__){
				if ("__direction__" == "ref2tar"){
					objElement->linkModuleName->o
				}
    			else if ("__direction__" == "tar2ref"){
					o->linkModuleName->objElement
				}
			}
		}
	}
}

save(refModule)
save(targetModule)

close(output)
close(refModule)
close(targetModule)
'''

    req_poc_linker = req_poc_linker.replace("__doors_dxl_output__", DXL_OUTPUT_PATH)
    req_poc_linker = req_poc_linker.replace("__ref_module_name__", ref_module_name)
    req_poc_linker = req_poc_linker.replace("__link_module_name__", link_module_name)
    req_poc_linker = req_poc_linker.replace("__target_module_name__", target_module_name)
    req_poc_linker = req_poc_linker.replace("__ref_attr_poc__", ref_attr_poc)
    req_poc_linker = req_poc_linker.replace("__ref_attr_req__", ref_attr_req)
    req_poc_linker = req_poc_linker.replace("__target_attr_poc__", target_attr_poc)
    req_poc_linker = req_poc_linker.replace("__start_index__", start_index)
    req_poc_linker = req_poc_linker.replace("__text_length__", text_length)
    req_poc_linker = req_poc_linker.replace("__direction__", direction)
    req_poc_linker = req_poc_linker.replace("__activeness__", activeness)
    
    return req_poc_linker