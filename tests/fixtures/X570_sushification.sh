#!/bin/sh
#Please execute only on a server running Sushi, e.g. fgcz-h-036
cd /srv/sushi/production/master

INPUT_DATASET_ID=$(bundle exec sushi_fabric --dataset /srv/gstore/projects/p10001/o12345_NovaSeq_261016_X570/dataset.tsv --run --input_dataset_application 390 --project 10001 --dataset_name o12345_NovaSeq_261016_X570 --mango_run_name o12345_X570 2> /dev/null | tr -d '\n')
bundle exec sushi_fabric --class FastqcApp --run --dataset_id $INPUT_DATASET_ID --parameterset /srv/GT/analysis/datasets/parameters_FastqcPE.tsv --project 10001 --next_dataset_name o12345_Fastqc
bundle exec sushi_fabric --class FastqScreenApp --run --dataset_id $INPUT_DATASET_ID --parameterset /srv/GT/analysis/datasets/parameters_FastqScreenPE.tsv --project 10001 --next_dataset_name o12345_FastqScreen

INPUT_DATASET_ID=$(bundle exec sushi_fabric --dataset /srv/gstore/projects/p10002/o12399_NovaSeq_261016_X570/dataset.tsv --run --input_dataset_application 390 --project 10002 --dataset_name o12399_NovaSeq_261016_X570 --mango_run_name o12399_X570 2> /dev/null | tr -d '\n')

cd /misc/GT/analysis/datasets
mv X570* processed