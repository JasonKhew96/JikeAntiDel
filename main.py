from datetime import datetime
from queue import Queue
from telegram.ext import Updater
from telegram import InputMediaPhoto, InputMediaAnimation
from telegram.error import TimedOut, BadRequest, TelegramError
from threading import Thread
from urllib.parse import urlparse
import logging
import os
import requests
import time
import traceback


class JikeAntiDel:
    def __init__(self, chat_id, bot_token):
        self.logger = logging.getLogger()

        self.chat_id = chat_id
        self.updater = Updater(
            token=bot_token,
            request_kwargs={'read_timeout': 20, 'connect_timeout': 20}
        )

        self.session = requests.Session()

        self.queue = Queue()
        self.thread = Thread(target=self.worker, args=(self.queue,))
        self.thread.setDaemon(True)
        self.thread.start()

        self.logger.info("Bot started")

        self.run()

    def download(self, url):
        while True:
            try:
                self.logger.debug("download")
                path = "media{}".format(urlparse(url).path)

                if not os.path.exists(path):
                    resp = self.session.get(url)
                    if resp.ok:
                        actualLen = resp.raw.tell()
                        expectedLen = int(resp.headers['Content-Length'])

                        if not actualLen < expectedLen:
                            with open(path, 'wb') as f:
                                f.write(resp.content)

                            self.logger.debug("Path dled: {}".format(path))
                            return path
                else:
                    self.logger.debug("Path exists: {}".format(path))
                    return path
                self.logger.error("re-download")
                time.sleep(5)

            except Exception as e:
                self.logger.error(e)
                time.sleep(5)

    def download_medias(self, medias):
        input_medias = []
        for url in medias:
            path = self.download(url)
            with open(path, "rb") as f:
                if 'gif' in path:
                    input_medias.append(InputMediaAnimation(media=f))
                else:
                    input_medias.append(InputMediaPhoto(media=f))
        return input_medias

    def sendPhoto(self, chat_id, picUrl):
        while True:
            try:
                self.logger.debug("sendPhoto")
                path = self.download(picUrl)
                with open(path, "rb") as f:
                    if 'gif' in path:
                        self.updater.bot.send_document(
                            chat_id=chat_id,
                            document=f,
                            disable_notification=True)
                    else:
                        self.updater.bot.send_photo(chat_id=chat_id,
                                                    photo=f,
                                                    disable_notification=True)
                break
            except TimedOut as e:
                self.logger.error("TimedOut")
                time.sleep(5)
            except BadRequest as e:
                self.logger.error("BadRequest: {}".format(e))
                break
            except TelegramError as e:
                self.logger.error("TelegramError: {}".format(e))
                break

    def sendMediaGroup(self, chat_id, medias):
        while True:
            try:
                self.logger.debug("sendMediaGroup")
                input_medias = self.download_medias(medias)
                self.updater.bot.send_media_group(chat_id=chat_id,
                                                  media=input_medias,
                                                  disable_notification=True)
                break
            except TimedOut as e:
                self.logger.error("TimedOut")
                time.sleep(5)
            except BadRequest as e:
                self.logger.error("BadRequest: {}".format(e))
                break

    def sendVideo(self, chat_id, video):
        while True:
            try:
                self.updater.bot.send_video(chat_id=chat_id,
                                            video=video,
                                            disable_notification=True)
                break
            except TimedOut as e:
                self.logger.error("TimedOut")
                time.sleep(5)
            except BadRequest as e:
                self.logger.error("BadRequest: {}".format(e))
                break

    def workerNotify(self, data):
        disablePreview = True
        screenName = data['user']['screenName']
        createdAt = data['createdAt']
        content = data['content']
        text = "{}\n{}\n\n{}\n".format(screenName,
                                       createdAt,
                                       content)

        self.logger.debug("screenName: {}".format(screenName))
        self.logger.debug("createdAt: {}".format(createdAt))
        self.logger.debug("content: {}".format(content))

        if len(data['pictures']) == 1:
            picUrl = data['pictures'][0]['picUrl']
            self.logger.debug("picUrl: {}".format(picUrl))
            self.sendPhoto(self.chat_id, picUrl)
            text = "{}\nPhoto:\n{}".format(text, picUrl)
            time.sleep(1)

        elif len(data['pictures']) > 1:
            medias = []
            text = "{}\nPhotos:".format(text)

            for pic in data['pictures']:
                picUrl = pic['picUrl']
                text = "{}\n{}".format(text, picUrl)
                self.logger.debug("picUrl: {}".format(picUrl))
                medias.append(picUrl)

            self.sendMediaGroup(self.chat_id, medias)
            time.sleep(1)

        if 'poi' in data:
            latitude = data['poi']['location'][1]
            longitude = data['poi']['location'][0]
            self.updater.bot.send_location(chat_id=self.chat_id,
                                           latitude=latitude,
                                           longitude=longitude,
                                           disable_notification=True)
            self.logger.debug("latitude: {}".format(latitude))
            self.logger.debug("longitude: {}".format(longitude))
            time.sleep(1)

        if 'linkInfo' in data:
            linkUrl = data['linkInfo']['linkUrl']
            text = "{}\nLink: {}".format(text, linkUrl)
            self.logger.debug("linkUrl: {}".format(linkUrl))
            disablePreview = False

        if 'video' in data:
            vidUrl = self.getVideoUrl(data['id'])
            text = "{}\nVideo: {}".format(text, vidUrl)
            # self.sendVideo(self.chat_id, vidUrl)
            self.logger.debug("vidUrl: {}".format(vidUrl))
            time.sleep(1)

        time.sleep(1)
        self.updater.bot.send_message(chat_id=self.chat_id,
                                      text=text,
                                      disable_web_page_preview=disablePreview)

    def worker(self, q):
        while True:
            time.sleep(5)
            item = q.get()
            self.workerNotify(item)
            q.task_done()

    def getVideoUrl(self, postId):
        url = "https://app.jike.ruguoapp.com/1.0/" \
              "mediaMeta/play?type=ORIGINAL_POST&id={}".format(postId)
        resp = self.session.post(url)
        vidUrl = resp.json()['url']
        return vidUrl

    def processData(self, datas, cache_time):
        if len(datas) <= 1:
            return 0.0
        for data in datas:
            username = data['user']['username']
            timestamp = datetime.strptime(data['createdAt'],
                                          "%Y-%m-%dT%H:%M:%S.%fZ").timestamp()
            if (username != 'forumadmin' and cache_time >= timestamp):
                break
            if (username != 'forumadmin'):
                self.queue.put(data)

        cache_time = datetime.strptime(datas[0]['createdAt'],
                                       "%Y-%m-%dT%H:%M:%S.%fZ").timestamp()
        return cache_time

    def run(self):
        isFirstTime = True
        cacheTimeDel = 0.0
        cacheTimeNight = 0.0
        # isJikeDown = False

        while True:
            timeNow = time.time()
            timeNext = timeNow + 60

            url = 'https://app.jike.ruguoapp.com/1.0/squarePosts/list'
            headers = {"Content-Type": "application/json"}
            dataDel = {"orderBy": "time",
                       "loadMoreKey": "null",
                       "topicId": "5aa4b7b0f69aa8001767430c",
                       "limit": 10}
            respDel = self.session.post(url, dataDel, headers)

            time.sleep(5)

            dataNight = {"orderBy": "time",
                         "loadMoreKey": "null",
                         "topicId": "58edf908937e150012f846ab",
                         "limit": 10}
            respNight = self.session.post(url, dataNight, headers)

            if (respDel.status_code == 200 and
                    respNight.status_code == 200):

                # if isJikeDown:
                #     self.updater.bot.send_message(chat_id=self.chat_id,
                #                                   text="即刻回来了！！！")
                #     self.logger.info("Jike is up")
                #     isJikeDown = False

                jsonDel = respDel.json()['data']
                jsonNight = respNight.json()['data']

                if not isFirstTime:
                    cacheTimeDel = self.processData(jsonDel,
                                                    cacheTimeDel)
                    cacheTimeNight = \
                        self.processData(jsonNight,
                                         cacheTimeNight)
                else:
                    if len(jsonDel) > 1:
                        cacheTimeDel = \
                            datetime.strptime(
                                jsonDel[0]['createdAt'],
                                "%Y-%m-%dT%H:%M:%S.%fZ").timestamp()
                    if len(jsonNight) > 1:
                        cacheTimeNight = \
                            datetime.strptime(
                                jsonNight[0]['createdAt'],
                                "%Y-%m-%dT%H:%M:%S.%fZ").timestamp()
                    isFirstTime = False

            # elif not isJikeDown:
            #     isJikeDown = True
            #     self.updater.bot.send_message(chat_id=self.chat_id,
            #                                   text="即刻崩了？？？")
            #     self.logger.info("Jike down???")

            timeNow = time.time()
            timeSleep = timeNext - timeNow
            time.sleep(1 if timeSleep <= 0 else timeSleep)


if __name__ == '__main__':
    chat_id = '1231231231'
    bot_token = '1242424234'
    try:
        format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        logging.basicConfig(level=logging.DEBUG,
                            format=format)
        JikeAntiDel(chat_id, bot_token)
    except Exception as e:
        time.sleep(10)
        updater = Updater(token=bot_token)
        updater.bot.send_message(chat_id=chat_id,
                                 text="Bot Crashed!!!")
        print(e)
        var = traceback.format_exc()
        print(var)
        # updater.bot.send_message(chat_id=chat_id,
        #                          text="Log: \n" + var,)
