import os
import shutil
import datetime
import zipfile
from urllib import request as req
import tensorflow as tf
import tensorflow_addons as tfa
from numba import cuda
import requests

class Model:
    __epochs = 10
    __batch_size = 32
    __validation_split = 0.3
    __early_stop = None
    __learning_rate_reduction = True
    __config = None
    __user_id = None
    __train_id = None
    __project_no = None
    model = None

    def __init__(self, config, uid, train_id, project_no):
        print(config)
        self.__config = config
        self.__epochs = config['epochs']
        self.__batch_size = config['batch_size']
        self.__early_stop = config['early_stop']
        self.__learning_rate_reduction = config['learning_rate_reduction']
        self.__user_id = uid
        self.__train_id = train_id
        self.__project_no = project_no
        convert_server = os.environ['CONVERT_SERVER']
        self.model = get_model_from_url(f'http://{convert_server}/api/model', uid)

    def __get_callbacks(self):
        callbacks = []

        if self.__early_stop['usage']:
            early_stop = tf.keras.callbacks.EarlyStopping(
                monitor=self.__early_stop['monitor'],
                patience=self.__early_stop['patience']
            )
            callbacks.append(early_stop)

        if self.__learning_rate_reduction['usage']:
            learning_rate_reduction = tf.keras.callbacks.ReduceLROnPlateau(
                monitor=self.__learning_rate_reduction['monitor'],
                patience=self.__learning_rate_reduction['patience'],
                verbose=1,
                factor=self.__learning_rate_reduction['factor'],
                min_lr=self.__learning_rate_reduction['min_lr']
            )
            callbacks.append(learning_rate_reduction)

        remote_monitor = tf.keras.callbacks.RemoteMonitor(
            root=f'https://{os.environ["API_SERVER"]}',
            path=f'/api/project/{self.__project_no}/train/{self.__train_id}/epoch',
            field='data',
            headers={'train_id': str(self.__train_id)},
            send_as_json=True
        )
        callbacks.append(remote_monitor)

        return callbacks

    def fit(self, data, label, kind):
        callbacks = self.__get_callbacks()

        print('start training')

        if kind == 'IMAGES':
            self.model.fit(
                data[0],
                validation_data=data[1],
                epochs=self.__epochs,
                batch_size=self.__batch_size,
                callbacks=callbacks,
                verbose=1
            )
        else:
            self.model.fit(
                data[0], label[0],
                validation_data=(data[1], label[1]),
                epochs=self.__epochs,
                batch_size=self.__batch_size,
                validation_split=self.__validation_split,
                callbacks=callbacks,
                verbose=1
            )

        print('train finished')
        try:
            shutil.rmtree('./dataset')
        except:
            None

        return

    def save_model(self):
        current = datetime.datetime.now()
        model_path = f'{self.__user_id}/{current.strftime("%Y%m%d-%H-%M-%S")}'
        self.model.save(model_path)

        # zip model
        zip_name = f'{self.__user_id}-{current.strftime("%Y%m%d-%H-%M-%S")}'
        shutil.make_archive(zip_name, 'zip', f'./{model_path}')

        # post model to api server
        model_file = open(f'./{zip_name}.zip', 'rb')
        file = {'model': model_file}

        res = requests.post(f'https://{os.environ["API_SERVER"]}/api/train/{self.__train_id}/model', files=file)
        print(f'response from save model api : {res}')

        model_file.close()

        # Remove model.
        shutil.rmtree(f'./{self.__user_id}/Model')
        shutil.rmtree(f'./{self.__user_id}')
        os.remove('./Model.zip')
        os.remove(f'./{zip_name}.zip')

        return res


def get_model_from_url(url, id):
    # Get Saved model and Unzip
    header = {
        'id': id
    }

    r = req.Request(url, headers=header)

    model = open('./Model.zip', 'wb')
    model.write(req.urlopen(r).read())
    model.close()

    with zipfile.ZipFile('./Model.zip', 'r') as zip_ref:
        zip_ref.extractall('./')
        print('extracting...')

    # Load model
    model = tf.keras.models.load_model(f'./{id}/Model',  custom_objects={'Addons>AdamW': tfa.optimizers.AdamW})

    return model
