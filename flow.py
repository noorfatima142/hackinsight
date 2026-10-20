from prefect import flow, task
import pipeline, publish

@task(retries=2, retry_delay_seconds=120)
def refresh():
    pipeline.run(fresh=False)

@task(retries=1, retry_delay_seconds=60)
def push():
    publish.push()

@flow(name="hackinsight-hourly", log_prints=True)
def hourly():
    refresh()
    push()

if __name__ == "__main__":
    hourly.serve(name="hourly-at-5-past", cron="5 * * * *")