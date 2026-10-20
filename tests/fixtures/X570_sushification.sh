#!/bin/sh
#Please execute only on a server running Sushi, e.g. fgcz-h-036
cd /srv/sushi/production/master

INPUT_DATASET_ID=$(bundle exec sushi_fabric --dataset /srv/gstore/projects/p38192/o43291_NovaSeq_261016_X570/dataset.tsv --run --input_dataset_application 390 --project 38192 --dataset_name o43291_NovaSeq_261016_X570 --mango_run_name o43291_X570 2> /dev/null | tr -d '\n')
bundle exec sushi_fabric --class FastqcApp --run --dataset_id $INPUT_DATASET_ID --parameterset /srv/GT/analysis/datasets/parameters_FastqcPE.tsv --project 38192 --next_dataset_name o43291_Fastqc
bundle exec sushi_fabric --class FastqScreenApp --run --dataset_id $INPUT_DATASET_ID --parameterset /srv/GT/analysis/datasets/parameters_FastqScreenPE.tsv --project 38192 --next_dataset_name o43291_FastqScreen

INPUT_DATASET_ID=$(bundle exec sushi_fabric --dataset /srv/gstore/projects/p41576/o43383_NovaSeq_261016_X570/dataset.tsv --run --input_dataset_application 390 --project 41576 --dataset_name o43383_NovaSeq_261016_X570 --mango_run_name o43383_X570 2> /dev/null | tr -d '\n')

cd /misc/GT/analysis/datasets
mv X570* processed