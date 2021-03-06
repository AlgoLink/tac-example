from datetime import timedelta

import luigi
from luigi.contrib.s3 import S3Target
from luigi.contrib.kubernetes import KubernetesJobTask
import os

IMAGE = "tac-example:v1"
BUCKET = os.environ['S3_BUCKET']


class SourceData(luigi.ExternalTask):
    date = luigi.DateParameter()

    def output(self):
        return S3Target(
            path='s3://{bucket}/tac-example/source/{date:%Y-%m-%d}.csv'
                 .format(bucket=BUCKET, date=self.date)
        )

    def complete(self):
        """Hack so we don't have to create input files manually.

        Luigi will always think that this task is done, without checking for
        presence of source files.
        """
        return True


class FetchData(KubernetesJobTask):
    date = luigi.DateParameter()

    @property
    def name(self):
        return 'transform-data'

    @property
    def spec_schema(self):
        return {
            "containers": [{
                "name": self.name,
                "image": IMAGE,
                "command": self.cmd
            }],
        }

    def requires(self):
        return SourceData(date=self.date)

    def output(self):
        return S3Target(
            path='s3://{bucket}/tac-example/data/raw/{date:%Y-%m-%d}.csv'
                 .format(bucket=BUCKET, date=self.date)
        )

    @property
    def cmd(self):
        command = ['python', '-m', 'tac.fetch',
                   self.input().path, self.output().path]
        return command


class TransformData(KubernetesJobTask):
    date = luigi.DateParameter()

    @property
    def name(self):
        return 'transform-data'

    @property
    def spec_schema(self):
        return {
            "containers": [{
                "name": self.name,
                "image": IMAGE,
                "command": self.cmd
            }],
        }

    def requires(self):
        for delta in range(1, 11):
            yield FetchData(date=self.date - timedelta(days=delta))

    def output(self):
        return S3Target(
            path='s3://{bucket}/tac-example/data/transformed/{date:%Y-%m-%d}.csv'
                 .format(bucket=BUCKET, date=self.date)
        )

    @property
    def cmd(self):
        command = ['python', '-m', 'tac.transform', self.output().path]
        command += [item.path for item in self.input()]
        return command


class Predict(KubernetesJobTask):
    date = luigi.DateParameter()
    model_name = luigi.Parameter()

    @property
    def name(self):
        return 'predict'

    @property
    def spec_schema(self):
        return {
            "containers": [{
                "name": self.name,
                "image": IMAGE,
                "command": self.cmd
            }],
        }

    def requires(self):
        return TransformData(date=self.date)

    def output(self):
        return S3Target(
            path='s3://{bucket}/tac-example/data/predictions/{date:%Y-%m-%d}_{model}.csv'
                 .format(bucket=BUCKET, date=self.date, model=self.model_name)
        )

    @property
    def cmd(self):
        command = ['python', '-m', 'tac.predict',
                   self.model_name, self.input().path, self.output().path]
        return command


class MakePredictions(luigi.WrapperTask):
    date = luigi.DateParameter()

    def requires(self):
        for model_name in ['A', 'B']:
            yield Predict(date=self.date, model_name=model_name)
