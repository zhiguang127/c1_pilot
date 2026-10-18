"""Isolated Silver CLI; cannot import or write human Gold."""
import argparse
import json
import traceback

from .api import SILVER, SilverClient
from ..src.common import now, write


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('prepare'); sub.add_parser('source-audit'); sub.add_parser('evidence-audit')
    sub.add_parser('forecast'); sub.add_parser('summarize');sub.add_parser('revalidate');sub.add_parser('format-probe');sub.add_parser('freeze-release')
    a=sub.add_parser('annotate');a.add_argument('--scope',choices=['smoke','heldout'],default='smoke')
    a=sub.add_parser('budget');a.add_argument('--cap-cny',type=float,default=5.);a.add_argument('--max-calls',type=int,default=48)
    a=sub.add_parser('authorize-batch');a.add_argument('--cap-cny',type=float,required=True);a.add_argument('--max-calls',type=int,required=True);a.add_argument('--authorization-note',required=True)
    args=p.parse_args()
    try:
        if args.command=='prepare':
            from .sources import prepare
            r=prepare();out={k:r[k] for k in ['plan_id','version','knowledge_ids']};out['heldout_windows']=len(r['heldout_case_ids'])
        elif args.command=='budget':
            r=SilverClient().initialize(cap_cny=args.cap_cny,max_calls=args.max_calls);out={k:r[k] for k in ['cap_cny','max_calls','batch_authorized']}
        elif args.command=='authorize-batch':
            SilverClient().authorize_batch(cap_cny=args.cap_cny,max_calls=args.max_calls,authorization_note=args.authorization_note);out={'authorized':True}
        elif args.command=='source-audit':
            from .pipeline import source_audit
            out=source_audit()
        elif args.command=='annotate':
            from .pipeline import annotate
            out=annotate(args.scope)
        elif args.command=='forecast':
            from .pipeline import forecast
            out=forecast()
        elif args.command=='revalidate':
            from .pipeline import revalidate
            from .evidence import revalidate_evidence
            out={**revalidate(),**revalidate_evidence()}
        elif args.command=='format-probe':
            from .probes import format_probe
            out=format_probe()
        elif args.command=='freeze-release':
            from .release import freeze_release
            out=freeze_release()
        elif args.command=='evidence-audit':
            from .evidence import audit_evidence
            out=audit_evidence()
        else:
            from .report import build
            out=build()
        print(json.dumps(out,ensure_ascii=True))
    except Exception as exc:
        # Detailed exception/traceback remains in the private Silver directory.
        write(SILVER/'errors'/(now().replace(':','-')+'.json'),{'type':type(exc).__name__,'traceback':traceback.format_exc()})
        p.exit(2,'Silver stopped: '+type(exc).__name__+'; inspect private error log, no label fabricated.\n')


if __name__=='__main__':
    main()
