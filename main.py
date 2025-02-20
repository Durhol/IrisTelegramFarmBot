import time
import asyncio
import logging
import re
import sys
import os
from telethon import TelegramClient, events, utils
from datetime import datetime, timedelta
from telethon.errors import FloodWaitError, SessionPasswordNeededError
from telethon.tl.types import PeerChat, PeerChannel

if sys.platform == 'win32':
    os.system('chcp 65001')

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('iris_farm.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

API_ID = ''
API_HASH = ''
PHONE_NUMBER = ''
IRIS_BOT_USERNAME = 'iris_cm_bot'
GROUP_ID = -100
FARM_COMMAND = 'Фарма'

SUCCESS_PATTERN = r'ЗАЧЁТ'
FAILURE_PATTERN = r'НЕЗАЧЁТ.*через\s+(\d+)\s+час(?:а|ов)?\s+(\d+)\s+мин'

class IrisFarmer:
    def __init__(self):
        self.client = None
        self.next_farm_time = datetime.now()
        self.retry_interval = timedelta(minutes=2)
        self.normal_interval = timedelta(hours=4)
        self.running = True
        self.iris_bot_id = None

    async def initialize(self):
        self.client = TelegramClient('iris_session', API_ID, API_HASH)
        
        try:
            await self.client.connect()
            logger.info("Подключение к серверам Телеграм установлено")
            
            if not await self.client.is_user_authorized():
                logger.info("Требуется авторизация")
                await self.client.send_code_request(PHONE_NUMBER)
                try:
                    code = input('Введи полученный код: ')
                    await self.client.sign_in(PHONE_NUMBER, code)
                except SessionPasswordNeededError:
                    password = input('Введи пароль двухфакторной аутентификации: ')
                    await self.client.sign_in(password=password)
                logger.info("Авторизация успешна")
            else:
                logger.info("Уже авторизован, продолжаем работу")
            
            entity = await self.client.get_entity(IRIS_BOT_USERNAME)
            self.iris_bot_id = entity.id
            logger.info(f"ID бота Ирис: {self.iris_bot_id}")
            
            try:
                group_entity = await self.client.get_entity(GROUP_ID)
                logger.info(f"Группа найдена: {utils.get_display_name(group_entity)}")
            except Exception as e:
                logger.error(f"Ошибка доступа к группе: {e}")
                logger.info("Пытаемся получить список всех доступных диалогов...")
                
                dialogs = await self.client.get_dialogs()
                logger.info("Доступные диалоги:")
                for dialog in dialogs:
                    entity_type = "Чат" if isinstance(dialog.entity, PeerChat) else "Канал" if isinstance(dialog.entity, PeerChannel) else "Пользователь"
                    logger.info(f"ID: {dialog.entity.id}, Тип: {entity_type}, Название: {dialog.name}")
                
                raise Exception("Не могу получить доступ к указанной группе. Проверь ID группы.")
            
            @self.client.on(events.NewMessage(from_users=self.iris_bot_id, chats=GROUP_ID))
            async def message_handler(event):
                await self.handle_response(event)
            
            logger.info("Обработчик сообщений настроен, начинаем цикл фарминга")
            asyncio.create_task(self.farming_loop())
            logger.info(f"Следующий фарм запланирован на: {self.next_farm_time}")
            await self.client.run_until_disconnected()
            
        except Exception as e:
            logger.error(f"Критическая ошибка при инициализации: {e}")
            self.restart()
    
    async def handle_response(self, event):
        message_text = event.message.text
        logger.info(f"Получено сообщение от Ирис: {message_text}")
        
        if match := re.search(FAILURE_PATTERN, message_text):
            hours = int(match.group(1))
            minutes = int(match.group(2))
            wait_time = timedelta(hours=hours, minutes=minutes)
            self.next_farm_time = datetime.now() + wait_time
            logger.info(f"❌ Фарм не удался. Следующая попытка через {hours} ч {minutes} мин ({self.next_farm_time})")
            return
        elif re.search(SUCCESS_PATTERN, message_text):
            logger.info("✅ Фарм успешен! Следующий через 4 часа")
            self.next_farm_time = datetime.now() + self.normal_interval
            logger.info(f"Следующий фарм в: {self.next_farm_time}")
        else:
            logger.warning(f"⚠️ Непонятный ответ от Ирис. Текст: {message_text}")
            self.next_farm_time = datetime.now() + self.retry_interval
            logger.info(f"Повторная попытка через {self.retry_interval.total_seconds() / 60} мин ({self.next_farm_time})")
    
    async def send_farm_command(self):
        try:
            logger.info(f"Отправка команды '{FARM_COMMAND}' в группу {GROUP_ID}")
            await self.client.send_message(GROUP_ID, FARM_COMMAND)
            logger.info("Команда отправлена успешно")
        except FloodWaitError as e:
            wait_seconds = e.seconds
            logger.warning(f"⚠️ Ограничение скорости! Ожидание {wait_seconds} сек")
            self.next_farm_time = datetime.now() + timedelta(seconds=wait_seconds + 10)
            logger.info(f"Следующая попытка в: {self.next_farm_time}")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки команды: {e}")
            self.next_farm_time = datetime.now() + self.retry_interval
            logger.info(f"Повторная попытка через {self.retry_interval.total_seconds() / 60} мин ({self.next_farm_time})")
    
    async def farming_loop(self):
        logger.info("Запущен цикл фарминга")
        while self.running:
            try:
                current_time = datetime.now()
                time_left = (self.next_farm_time - current_time).total_seconds()
                
                if time_left <= 0:
                    logger.info("Время для фарма!")
                    await self.send_farm_command()
                else:
                    if time_left % 600 < 30:
                        hours, remainder = divmod(time_left, 3600)
                        minutes, seconds = divmod(remainder, 60)
                        logger.info(f"Ожидание до следующего фарма: {int(hours)}ч {int(minutes)}м {int(seconds)}с")
                
                await asyncio.sleep(10)
            except Exception as e:
                logger.error(f"Ошибка в цикле фарминга: {e}")
                await asyncio.sleep(60)
                self.restart()
    
    def restart(self):
        logger.info("🔄 Перезапуск бота...")
        time.sleep(5)
        python = sys.executable
        os.execl(python, python, *sys.argv)

async def main():
    farmer = IrisFarmer()
    await farmer.initialize()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.critical(f"Критическая ошибка: {e}")
        time.sleep(10)
        python = sys.executable
        os.execl(python, python, *sys.argv)