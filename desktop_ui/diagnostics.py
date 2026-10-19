"""Local-only environment receipt. Does not execute models or operate applications."""
import argparse,datetime,json,platform,shutil,subprocess,urllib.request
from pathlib import Path
import psutil

def collect():
    report={'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'os':platform.platform(),'python':platform.python_version(),'cpu':platform.processor(),'logical_cpu_count':psutil.cpu_count(),'physical_cpu_count':psutil.cpu_count(logical=False),'memory':dict(psutil.virtual_memory()._asdict()),'gpu':[],'errors':[],'target_hardware_verified':False,'release_approved':False}
    if platform.system()=='Windows':
        command='Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion,AdapterRAM | ConvertTo-Json -Compress'
        try:
            result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],capture_output=True,text=True,encoding='utf8',errors='replace',timeout=20,check=True)
            values=json.loads(result.stdout);report['gpu']=values if isinstance(values,list) else [values]
            report['gpu_memory_note']='Win32 AdapterRAM may truncate dedicated VRAM above 4GB. It is not accepted as target VRAM proof.'
        except Exception as exc:report['errors'].append('GPU inventory: '+str(exc))
    smi=shutil.which('nvidia-smi')
    if smi:
        try:
            result=subprocess.run([smi,'--query-gpu=name,memory.total,driver_version','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=10,check=True)
            report['nvidia_smi']=[dict(zip(('name','dedicated_vram_mib','driver'),[s.strip() for s in line.split(',')])) for line in result.stdout.strip().splitlines()]
        except Exception as exc:report['errors'].append('nvidia-smi: '+str(exc))
    try:
        with urllib.request.urlopen('http://127.0.0.1:11434/api/ps',timeout=3) as response:data=json.load(response)
        report['loaded_models']=[{k:m.get(k) for k in ('name','digest','size','size_vram','context_length')} for m in data.get('models',[])]
    except Exception as exc:report['errors'].append('Local inference service: '+str(exc))
    report['scope']='One local environment snapshot, no serial numbers/accounts/audio/screenshots. Loaded-model VRAM is allocation, not GPU capacity. No stability, latency, native-task or 24GB/6GB qualification is inferred.'
    return report

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():raise FileExistsError('Keep previous receipts; choose another output filename')
    report=collect();args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'report':str(args.output.resolve()),'ram_gib':round(report['memory']['total']/2**30,2),'gpu':[g.get('Name') for g in report['gpu']],'target_hardware_verified':False,'errors':report['errors']},ensure_ascii=False))

if __name__=='__main__':main()
