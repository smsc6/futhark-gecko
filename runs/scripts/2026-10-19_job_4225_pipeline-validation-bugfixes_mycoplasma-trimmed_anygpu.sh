#!/bin/bash
#SBATCH --job-name=pipeline-validation-bugfixes_mycoplasma-trimmed_anygpu_ram-4GB
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

# cudagecko validation copy with bug 2 and bug 3 fixed
cg=$results/2026-10-19_cudagecko-validation-copy-bugfixes_mycoplasma-trimmed_anygpu_ram-4GB_${SLURM_JOB_ID}
mkdir -p $cg
cd $cg
/home/cgf146/gecko/cudagecko-validation-copy/bin/gpu_cuda_workflow \
  -query $data/trimmed/NC_006360.1.trimmed.fasta \
  -ref   $data/trimmed/NC_021831.1.trimmed.fasta \
  -dev 0 \
  -ram 4000000000
ls -l $cg

# futhark-gecko full pipeline (gecko.fut binary built in job 4115)
fu=$results/2026-10-19_futhark-gecko-pipeline-vs-bugfixes_mycoplasma-trimmed_anygpu_${SLURM_JOB_ID}
mkdir -p $fu
cd $fu
cat $data/futhark-input/NC_006360.1.trimmed.in $data/futhark-input/NC_021831.1.trimmed.in \
  | $build/gecko -e gecko -b > futhark_pipeline_output.bin
ls -l $fu

# End-to-end comparison, both strands
python3 /home/cgf146/gecko/futhark-gecko/tools/compare_pipeline_with_cudagecko.py $fu $cg \
  | tee $results/2026-10-19_pipeline_comparison_bugfixes_mycoplasma-trimmed_${SLURM_JOB_ID}.txt
