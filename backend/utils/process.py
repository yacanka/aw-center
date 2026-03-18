from wmi import WMI
import subprocess
import os
from win32com.client import GetActiveObject, Dispatch
from win32com.client.gencache import EnsureDispatch
from time import sleep
#import win32com.client as wc

#wc.gencache.is_readonly = False
#wc.gencache.Rebuild()

def is_process_running(process_name):
    c = WMI()
    for process in c.Win32_Process():
        if process.Name.lower() == process_name.lower():
            return True
    return False

def start_exe(exe_path, params):
    exe_name = os.path.basename(exe_path)
    try:
        subprocess.Popen([exe_path] + params)
        print(f"'{exe_name}' started.")
    except Exception as e:
        print(f"Error while starting {exe_name}: {e}")
        
def get_or_run(com_name, executable, params, max_wait=15, sleep_interval=1):
    exe_name = os.path.basename(executable)
    if is_process_running(exe_name):
        #doors = EnsureDispatch(com_name)
        doors = Dispatch(com_name)
        return doors
    else:
        start_exe(executable, params)

        wait_time = 0
        while wait_time < max_wait:
            try:
                print(f"Attempt {wait_time + 1}: Connecting to {com_name}...")
                doors = GetActiveObject(com_name)
                print(f"{com_name} connection is successfull.")
                return doors
            except Exception as e:
                print(f"Attempt fail: {e}")
                sleep(sleep_interval)
                wait_time += sleep_interval
        else:
            print("Timeout: COM server is not ready.")
            raise TimeoutError(f"{com_name} COM server is not started.")