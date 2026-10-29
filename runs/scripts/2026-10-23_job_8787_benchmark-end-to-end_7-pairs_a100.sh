#!/bin/bash
#SBATCH --job-name=benchmark-end-to-end_7-pairs_a100
#SBATCH --partition=gpu
#SBATCH --gres=gpu:a100:1
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=06:00:00
#SBATCH --output=/home/cgf146/gecko/runs/logs/2026-10-23_%x_%j.out

module unload cuda
module load cuda/11.8
module load gcc/11.2.0
module load futhark/0.25.8

nvidia-smi
data=/home/cgf146/gecko/data
build=/home/cgf146/gecko/builds/futhark-gecko-cuda
out=/home/cgf146/gecko/runs/results/2026-10-23_benchmark-end-to-end_7-pairs_a100_${SLURM_JOB_ID}
mkdir -p $out

# Benchmark pairs from benchmarks/PROTOCOL.md (query, reference), trimmed inputs
names=(mycoplasma ecoli gallus-meleagris oryzias-danio sus-bos human-mouse-chrX human-gorilla-chr1)
queries=(NC_006360.1 NZ_CP014268.2 Gallus_gallus.WASHUC2.70.dna.chromosome.18 Oryzias_latipes.MEDAKA1.75.dna.chromosome.6 Sus_scrofa.Sscrofa11.1.dna.chromosome.11 Homo_sapiens.GRCh37.75.dna.chromosome.X Homo_sapiens.GRCh37.75.dna.chromosome.1)
refs=(NC_021831.1 NZ_CP009789.1 Meleagris_gallopavo.UMD2.dna.chromosome.20 Danio_rerio.GRCz11.dna.chromosome.25 Bos_taurus.UMD3.1.dna.chromosome.12 Mus_musculus.GRCm38.dna.chromosome.X Gorilla_gorilla.gorGor3.1.75.dna.chromosome.1)

# Stop before any GPU work if an input file is missing
for f in ${queries[@]} ${refs[@]}; do
  for p in $data/trimmed/$f.trimmed.fasta $data/futhark-input/$f.trimmed.in; do
    if [ ! -f $p ]; then echo "MISSING INPUT: $p"; exit 1; fi
  done
done
echo "all 28 input files present"

# cudagecko builds: original, and original with bugs 2 and 3 fixed
programs=(cudagecko-original cudagecko-bugfixed)
binaries=(/home/cgf146/gecko/cudagecko/bin/gpu_cuda_workflow /home/cgf146/gecko/cudagecko-bugfixed/bin/gpu_cuda_workflow)

for i in ${!names[@]}; do
  q=${queries[$i]}
  r=${refs[$i]}

  # cudagecko: run 0 = warm-up (discarded), runs 1-10 timed
  # Stage times summed afterwards from each run log (tools/sum_cudagecko_stage_times.py)
  for j in ${!programs[@]}; do
    dir=$out/${programs[$j]}/${names[$i]}
    mkdir -p $dir
    cd $dir
    for run in $(seq 0 10); do
      start=$(date +%s.%N)
      ${binaries[$j]} -query $data/trimmed/$q.trimmed.fasta -ref $data/trimmed/$r.trimmed.fasta -dev 0 -ram 4000000000 > run_${run}.log 2>&1
      rc=$?
      end=$(date +%s.%N)
      echo "run $run exit $rc wall_s $(awk "BEGIN{print $end - $start}")" >> wall_times.txt
      # CSV not kept (disk space, PROTOCOL.md); deleted outside cudagecko's timed stages
      rm -f *.csv
    done
  done

  # Futhark: -r 10 = 1 warm-up run (not counted) + 10 timed runs in one process
  # -t writes one runtime per timed run (microseconds); output to /dev/null (disk space, PROTOCOL.md)
  # Batch size 32459520 = cudagecko words_at_once at -ram 4000000000; gecko binary compiled in job 4362
  dir=$out/futhark-gecko/${names[$i]}
  mkdir -p $dir
  cd $dir
  ( echo 32459520i64; cat $data/futhark-input/$q.trimmed.in $data/futhark-input/$r.trimmed.in ) \
    | $build/gecko -e gecko_batched -b -r 10 -t futhark_runtimes_microseconds.txt > /dev/null 2> futhark_stderr.log
  echo "futhark exit code: $?" > futhark_exit_code.txt
done
