#!/bin/bash
#SBATCH --job-name=nsys-profile_7-pairs_a100-80gb-pcie_hendrixgpu14fl
#SBATCH --partition=gpu
#SBATCH --gres=gpu:a100:1
#SBATCH --nodelist=hendrixgpu14fl
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=00:45:00
#SBATCH --output=/home/cgf146/gecko/runs/logs/2026-10-27_%x_%j.out

module unload cuda
module load cuda/11.8
module load gcc/11.2.0
module load futhark/0.25.8

nvidia-smi
data=/home/cgf146/gecko/data
build=/home/cgf146/gecko/builds/futhark-gecko-cuda
cudagecko=/home/cgf146/gecko/cudagecko/bin/gpu_cuda_workflow
out=/home/cgf146/gecko/runs/results/2026-10-27_nsys-profile_7-pairs_a100-80gb-pcie_hendrixgpu14fl_${SLURM_JOB_ID}

# Per-stage GPU times for all 7 benchmark pairs: one nsys-profiled run per pair, Futhark and original cudagecko
# nsys = kernel-only times and copy times, same method for both programs (cudagecko stage timers include copies and CPU work)
# Same trimmed inputs, -ram and batch size as job 8787; original cudagecko only (bug-fixed stage times within 2%, job 8787)
names=(mycoplasma ecoli gallus-meleagris oryzias-danio sus-bos human-mouse-chrX human-gorilla-chr1)
queries=(NC_006360.1 NZ_CP014268.2 Gallus_gallus.WASHUC2.70.dna.chromosome.18 Oryzias_latipes.MEDAKA1.75.dna.chromosome.6 Sus_scrofa.Sscrofa11.1.dna.chromosome.11 Homo_sapiens.GRCh37.75.dna.chromosome.X Homo_sapiens.GRCh37.75.dna.chromosome.1)
refs=(NC_021831.1 NZ_CP009789.1 Meleagris_gallopavo.UMD2.dna.chromosome.20 Danio_rerio.GRCz11.dna.chromosome.25 Bos_taurus.UMD3.1.dna.chromosome.12 Mus_musculus.GRCm38.dna.chromosome.X Gorilla_gorilla.gorGor3.1.75.dna.chromosome.1)

for i in ${!names[@]}; do
  q=${queries[$i]}
  r=${refs[$i]}

  # Futhark: input written to a file first so nsys profiles only the gecko process
  dir=$out/futhark-gecko/${names[$i]}
  mkdir -p $dir
  cd $dir
  ( echo 32459520i64; cat $data/futhark-input/$q.trimmed.in $data/futhark-input/$r.trimmed.in ) > input.in
  nsys profile --stats=true -o futhark_${names[$i]} sh -c "$build/gecko -e gecko_batched -b -t futhark_runtime_microseconds.txt < input.in > /dev/null" > nsys_stats.txt 2>&1
  echo "futhark ${names[$i]} nsys exit code: $?"
  rm -f input.in

  # Original cudagecko: CSV deleted after the run (disk space, PROTOCOL.md)
  dir=$out/cudagecko-original/${names[$i]}
  mkdir -p $dir
  cd $dir
  nsys profile --stats=true -o cudagecko_${names[$i]} $cudagecko -query $data/trimmed/$q.trimmed.fasta -ref $data/trimmed/$r.trimmed.fasta -dev 0 -ram 4000000000 > nsys_stats.txt 2>&1
  echo "cudagecko ${names[$i]} nsys exit code: $?"
  rm -f *.csv
done
