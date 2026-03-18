def find_missing_elements(list_to_check, reference_list, ignore_case=False):
    if ignore_case:
        list_to_check = [item.lower() for item in list_to_check]
        reference_list = [item.lower() for item in reference_list]
        
    missing_elements = [item for item in reference_list if item not in list_to_check]
    return missing_elements

def safe_get(arr, index, default=None):
    try:
        return arr[index]
    except (IndexError, TypeError):
        return default
    
def safe_get_nd(arr, indices, default=None):
    try:
        cur = arr
        for i in indices:
            cur = cur[i]
        return cur
    except (IndexError, TypeError):
        return default