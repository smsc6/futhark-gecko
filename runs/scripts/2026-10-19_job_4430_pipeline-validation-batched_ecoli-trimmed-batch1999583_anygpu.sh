#!/bin/bash
#SBATCH --job-name=pipeline-validation-batched_ecoli-trimmed-batch1999583_anygpu
#SBATCH --partition=gpu
#SBATCH --gres=gpu:1
#SBATCH --exclude=hendrixgpu09fl,hendrixgpu10fl,hendrixgpu17fl,hendrixgpu18fl
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=00:15:00
#SBATCH --output=/home/cgf146/gecko/runs/logs/2026-10-19_%x_%j.out

module unload cuda
module load cuda/11.8
module load gcc/11.2.0
module load futhark/0.25.8

nvidia-smi
data=/home/cgf146/gecko/data
results=/home/cgf146/gecko/runs/results
build=/home/cgf146/gecko/builds/futhark-gecko-cuda

# cudagecko validation copy (bugs 2 and 3 fixed, .bin files appended per batch)
# -ram 344807544 gives words_at_once = 1,999,583: 3 batches per sequence, all full 64-word blocks (bug 1 avoided)
cg=$results/2026-10-19_cudagecko-validation-copy-batched_ecoli-trimmed-batch1999583_anygpu_ram-344807544_${SLURM_JOB_ID}
mkdir -p $cg
cd $cg
/home/cgf146/gecko/cudagecko-validation-copy/bin/gpu_cuda_workflow \
  -query $data/trimmed/NZ_CP014268.2.trimmed-batch1999583.fasta \
  -ref   $data/trimmed/NZ_CP009789.1.trimmed-batch1999583.fasta \
  -dev 0 \
  -ram 344807544
ls -l $cg

# futhark-gecko gecko_batched entry, batch size 1999583 (same as cudagecko), gecko binary compiled in job 4362
fu=$results/2026-10-19_futhark-gecko-pipeline-batched_ecoli-trimmed-batch1999583_anygpu_${SLURM_JOB_ID}
mkdir -p $fu
cd $fu
( echo 1999583i64; cat $data/futhark-input/NZ_CP014268.2.trimmed-batch1999583.in $data/futhark-input/NZ_CP009789.1.trimmed-batch1999583.in ) \
  | $build/gecko -e gecko_batched -b > futhark_pipeline_output.bin
ls -l $fu

# End-to-end comparison, both strands
python3 /home/cgf146/gecko/futhark-gecko/tools/compare_pipeline_with_cudagecko.py $fu $cg \
  | tee $results/2026-10-19_pipeline_comparison_batched_ecoli-trimmed-batch1999583_${SLURM_JOB_ID}.txt