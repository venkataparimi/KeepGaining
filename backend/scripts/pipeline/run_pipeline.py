"""
Pipeline Runner: Orchestrates all 3 stages
Can run stages independently or together.
"""
import subprocess
import sys
import argparse
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent


def run_stage(stage_num: int, args: list = None):
    """Run a specific stage."""
    scripts = {
        1: 'stage1_compute.py',
        2: 'stage2_parquet.py',
        3: 'stage3_db_load.py'
    }
    
    script = SCRIPTS_DIR / scripts[stage_num]
    cmd = [sys.executable, str(script)] + (args or [])
    
    print(f"\n{'='*60}")
    print(f"RUNNING STAGE {stage_num}: {scripts[stage_num]}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'='*60}\n")
    
    result = subprocess.run(cmd)
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description='Indicator Pipeline Runner')
    parser.add_argument('--stage', type=int, choices=[1, 2, 3], help='Run specific stage only')
    parser.add_argument('--all', action='store_true', help='Run all stages sequentially')
    parser.add_argument('--workers', type=int, default=8, help='Workers for Stage 1 (default: 8)')
    parser.add_argument('--type', choices=['EQUITY', 'INDEX', 'FUTURES', 'CE', 'PE'], help='Instrument type filter')
    parser.add_argument('--limit', type=int, help='Limit number of instruments')
    parser.add_argument('--watch', action='store_true', help='Stage 2 watch mode')
    
    args = parser.parse_args()
    
    if args.stage:
        # Run specific stage
        stage_args = []
        if args.stage == 1:
            stage_args = ['--workers', str(args.workers)]
            if args.type:
                stage_args += ['--type', args.type]
            if args.limit:
                stage_args += ['--limit', str(args.limit)]
        elif args.stage == 2 and args.watch:
            stage_args = ['--watch']
        
        success = run_stage(args.stage, stage_args)
        sys.exit(0 if success else 1)
    
    elif args.all:
        # Run all stages sequentially
        stage1_args = ['--workers', str(args.workers)]
        if args.type:
            stage1_args += ['--type', args.type]
        if args.limit:
            stage1_args += ['--limit', str(args.limit)]
        
        print("\n" + "="*60)
        print("RUNNING FULL PIPELINE")
        print("="*60)
        
        if not run_stage(1, stage1_args):
            print("Stage 1 failed!")
            sys.exit(1)
        
        if not run_stage(2):
            print("Stage 2 failed!")
            sys.exit(1)
        
        if not run_stage(3):
            print("Stage 3 failed!")
            sys.exit(1)
        
        print("\n" + "="*60)
        print("PIPELINE COMPLETE!")
        print("="*60)
    
    else:
        parser.print_help()
        print("\n\nExamples:")
        print("  python run_pipeline.py --stage 1 --workers 8 --type EQUITY")
        print("  python run_pipeline.py --stage 2 --watch")
        print("  python run_pipeline.py --stage 3")
        print("  python run_pipeline.py --all --workers 8")


if __name__ == '__main__':
    main()
