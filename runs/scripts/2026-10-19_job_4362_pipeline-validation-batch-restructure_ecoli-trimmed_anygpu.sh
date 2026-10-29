#!/bin/bash
#SBATCH --job-name=pipeline-validation-batch-restructure_ecoli-trimmed_anygpu
#SBATCH --partition=gpu
#SBATCH --gres=gpu:1
#SBATCH --exclude=hendrixgpu09fl,hendrixgpu10fl,hendrixgpu17fl,hendrixgpu18fl
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=00:20:00
#SBATCH --output=/home/cgf146/gecko/runs/logs/2026-10-19_%x_%j.out

module unload cuda
module load cuda/11.8
module load gcc/11.2.0
module load futhark/0.25.8

nvidia-smi
data=/home/cgf146/gecko/data
results=/home/cgf146/gecko/runs/results
build=/home/cgf146/gecko/builds/futhark-gecko-cuda

# Compile gecko.fut with batch loop (gecko entry = one batch, should match job 4234)
cd /home/cgf146/gecko/futhark-gecko
futhark cuda -o $build/gecko gecko.fut
ls -l $build/gecko

# cudagecko validation copy output reused from job 4234 (cudagecko unchanged)
cg=$results/2026-10-19_cudagecko-validation-copy-bugfixes_ecoli-trimmed_anygpu_ram-4GB_4234
ls -l $cg

# futhark-gecko full pipeline, E. coli B (query) vs E. coli K12 (reference)
fu=$results/2026-10-19_futhark-gecko-pipeline-batch-restructure_ecoli-trimmed_anygpu_${SLURM_JOB_ID}
mkdir -p $fu
cd $fu
cat $data/futhark-input/NZ_CP014268.2.trimmed.in $data/futhark-input/NZ_CP009789.1.trimmed.in \
  | $build/gecko -e gecko -b > futhark_pipeline_output.bin
ls -l $fu

# End-to-end comparison, both strands
python3 /home/cgf146/gecko/futhark-gecko/tools/compare_pipeline_with_cudagecko.py $fu $cg \
  | tee $results/2026-10-19_pipeline_comparison_batch-restructure_ecoli-trimmed_${SLURM_JOB_ID}.txt