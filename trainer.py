import json
import urllib.error

import pika
from train import Model
from dataset import get_dataset
import tensorflow as tf
import requests
import os
from numba import cuda


class Trainer:
    connection = None
    channel = None
    queue = ''

    def __init__(self, host, queue):
        self.connection = pika.BlockingConnection(
            pika.ConnectionParameters(host=host, virtual_host=os.environ['VHOST']))
        self.channel = self.connection.channel()
        self.queue = queue

    def run(self):
        # self.channel.queue_declare(queue=self.queue)
        self.channel.basic_qos(prefetch_count=1)
        self.channel.basic_consume(queue=self.queue, on_message_callback=train_callback, auto_ack=True)

        print(' [*] Waiting for messages. To exit press CTRL+C')
        self.channel.start_consuming()


def train_callback(ch, method, props, body):
    data = None
    label = None

    req_body = json.loads(body)


    headers = {
        'Content-Type': 'application/json; charset=utf-8',
        'train_id': str(req_body['train_id'])
    }
    try:
        model = Model(req_body['config'], req_body['user_id'], req_body['train_id'], req_body['project_no'])
    except ValueError as e:
        res = {'status_code': 400, 'msg': e.args[0], 'train_id': req_body['train_id']}
        reply_request(f'https://{os.environ["API_SERVER"]}/api/project/{req_body["project_no"]}/train/{req_body["train_id"]}/reply', res, headers)
        return

    #data, label = get_dataset(req_body['data_set'], model.model)
    res = {'status_code': 200, 'msg': 'start loading dataset...', 'train_id': req_body['train_id']}
    reply_request(f'https://{os.environ["API_SERVER"]}/api/project/{req_body["project_no"]}/train/{req_body["train_id"]}/log', res, headers)

    try:
        data, label = get_dataset(req_body['data_set'], model.model)
    except:
        res = {'status_code': 400, 'msg': f'failed to get dataset from {req_body["data_set"]["train_uri"]}', 'train_id': req_body['train_id']}
        reply_request(f'https://{os.environ["API_SERVER"]}/api/project/{req_body["project_no"]}/train/{req_body["train_id"]}/reply', res, headers)
        return

    res = {'status_code': 200, 'msg': 'loading dataset finished', 'train_id': req_body['train_id']}
    reply_request(f'https://{os.environ["API_SERVER"]}/api/project/{req_body["project_no"]}/train/{req_body["train_id"]}/log', res, headers)

    try:
        model.fit(data, label, req_body['data_set']['kind'])
    except tf.errors.InvalidArgumentError as e:
        res = {'status_code': 500, 'msg': e, 'train_id': req_body['train_id']}
        reply_request(f'https://{os.environ["API_SERVER"]}/api/project/{req_body["project_no"]}/train/{req_body["train_id"]}/reply', res, headers)
        return
    except tf.errors.AbortedError as e:
        res = {'status_code': 500, 'msg': e, 'train_id': req_body['train_id']}
        reply_request(f'https://{os.environ["API_SERVER"]}/api/project/{req_body["project_no"]}/train/{req_body["train_id"]}/reply', res, headers)
        return
    except tf.errors.FailedPreconditionError as e:
        res = {'status_code': 500, 'msg': e, 'train_id': req_body['train_id']}
        reply_request(f'https://{os.environ["API_SERVER"]}/api/project/{req_body["project_no"]}/train/{req_body["train_id"]}/reply', res, headers)
        return
    except tf.errors.UnknownError as e:
        res = {'status_code': 500, 'msg': e, 'train_id': req_body['train_id']}
        reply_request(f'https://{os.environ["API_SERVER"]}/api/project/{req_body["project_no"]}/train/{req_body["train_id"]}/reply', res, headers)
        return
    except json.JSONDecodeError as e:
       res = {'status_code': 500, 'msg': e, 'train_id': req_body['train_id']}
       reply_request(
           f'https://{os.environ["API_SERVER"]}/api/project/{req_body["project_no"]}/train/{req_body["train_id"]}/reply',
           res, headers)
       return
    except ValueError as e :
        res = {'status_code': 500, 'msg': e.args[0], 'train_id': req_body['train_id']}
        reply_request(
            f'https://{os.environ["API_SERVER"]}/api/project/{req_body["project_no"]}/train/{req_body["train_id"]}/reply',
            res, headers)
        return
    except:
        print("error occurred while training.")
        res = {'status_code': 500, 'msg': 'internal server error while training', 'train_id': req_body['train_id']}
        reply_request(
            f'https://{os.environ["API_SERVER"]}/api/project/{req_body["project_no"]}/train/{req_body["train_id"]}/reply',
            res, headers)
        return

    try:
        model.save_model()
    except:
        res = {'status_code': 500, 'msg': 'OS error', 'train_id': req_body['train_id']}
        reply_request(f'https://{os.environ["API_SERVER"]}/api/project/{req_body["project_no"]}/train/{req_body["train_id"]}/reply', res, headers)
        return

    # for releasing GPU memory
    # device = cuda.get_current_device()
    # device.reset()

    res = {'status_code': 200, 'msg': 'Train finished successfully.', 'train_id': req_body['train_id']}
    reply_request(f'https://{os.environ["API_SERVER"]}/api/project/{req_body["project_no"]}/train/{req_body["train_id"]}/reply', res, headers)
    return


def reply_request(url, data, headers):
    data = json.dumps(data).encode('utf-8')
    try:
        res = requests.post(url, data=data, headers=headers)
    except urllib.error.URLError as e:
        return e
    else:
        return res
