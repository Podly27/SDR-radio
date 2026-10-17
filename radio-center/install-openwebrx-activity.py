#!/usr/bin/python3
"""Install a loopback-only metrics extension for this OpenWebRX version."""
import datetime, pathlib, shutil, subprocess
root=pathlib.Path('/usr/lib/python3/dist-packages/owrx')
target=root/'controllers/metrics.py'
source=pathlib.Path(__file__).with_name('openwebrx_activity.py')
helper=root/'radio_center_activity.py'
original=target.read_text()
old='        data = json.dumps(Metrics.getSharedInstance().getHierarchicalMetrics())'
new='''        metrics = Metrics.getSharedInstance().getHierarchicalMetrics()
        # Radio center: expose anonymous tuning only to the local dashboard.
        if self.handler.client_address[0] in ("127.0.0.1", "::1"):
            try:
                from owrx.radio_center_activity import snapshot
                metrics["radio_center_activity"] = snapshot()
            except Exception:
                metrics["radio_center_activity"] = {"error": "Stav naladění není dostupný"}
        data = json.dumps(metrics)'''
if new not in original and original.count(old)!=1:raise SystemExit('Unsupported OpenWebRX metrics controller; no files changed')
updated=original if new in original else original.replace(old,new)
compile(updated,str(target),'exec');compile(source.read_text(),str(helper),'exec')
changed=updated!=original or not helper.exists() or helper.read_bytes()!=source.read_bytes()
if changed:
 backup=pathlib.Path('/opt/radio-center/backups')/('openwebrx-activity-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S'))
 backup.mkdir(parents=True,exist_ok=True);shutil.copy2(target,backup/'metrics.py')
 if helper.exists():shutil.copy2(helper,backup/helper.name)
 shutil.copyfile(source,helper);helper.chmod(0o644);target.write_text(updated)
 if subprocess.run(['systemctl','is-active','--quiet','openwebrx.service']).returncode==0:
  subprocess.run(['systemctl','restart','openwebrx.service'],check=True)
 print('OpenWebRX telemetry installed; backup:',backup)
else:print('OpenWebRX telemetry already installed')
