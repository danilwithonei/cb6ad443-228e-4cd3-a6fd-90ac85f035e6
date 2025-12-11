import pika
from dynaconf import settings


connection = pika.BlockingConnection(
    pika.ConnectionParameters(
        host=settings.RABBITMQ_HOST,
        virtual_host='/',
        credentials=pika.PlainCredentials(settings.RABBITMQ_USER, settings.RABBITMQ_PASS)
    )
)
channel = connection.channel()

def callback(ch, method, properties, body):
    print(f"Получено: {body.decode()}")
    ch.basic_ack(delivery_tag=method.delivery_tag)

channel.basic_consume(queue='output_queue', on_message_callback=callback)
print("Ожидание сообщений. Нажмите Ctrl+C для выхода.")
channel.start_consuming()