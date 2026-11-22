import json, numpy as np, importlib.util, sys
sys.path.insert(0,'/tmp/cwm_adv_sci_xl0Fl5')
import emi_dip as E
base='/Users/Mike/Code/wcfoma/data/results/k_eff/termination_20261029/'
T=json.load(open(base+'term_result.json')); C=json.load(open(base+'confirm_result.json'))
def walk(d, depth=0, maxd=3, pre=''):
    if isinstance(d, dict):
        for k,v in d.items():
            if isinstance(v,(dict,list)) and depth<maxd:
                print(pre+str(k)+':'); walk(v, depth+1, maxd, pre+'  ')
            else:
                print(pre+f"{k}: {str(v)[:150]}")
    elif isinstance(d, list):
        print(pre+f"list[{len(d)}] {str(d)[:150]}")
print("TERM keys"); walk(T, maxd=1)
rk=list(T['runs'].keys()) if 'runs' in T else None
print(rk)
