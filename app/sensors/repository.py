from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.mongodb_client import MongoDBClient
from app.redis_client import RedisClient
from typing import List, Optional
import json

from . import models, schemas

def get_sensor(db: Session, sensor_id: int) -> Optional[models.Sensor]:
    return db.query(models.Sensor).filter(models.Sensor.id == sensor_id).first()

def get_sensor_by_name(db: Session, name: str) -> Optional[models.Sensor]:
    return db.query(models.Sensor).filter(models.Sensor.name == name).first()

def get_sensors(db: Session, skip: int = 0, limit: int = 100) -> List[models.Sensor]:
    return db.query(models.Sensor).offset(skip).limit(limit).all()

def create_sensor(db: Session, mongodb_client: MongoDBClient,sensor: schemas.SensorCreate) -> models.Sensor:
    db_sensor = models.Sensor(name=sensor.name)
    db.add(db_sensor)
    db.commit()
    db.refresh(db_sensor)
    add_collection(mongodb_client=mongodb_client,sensor=sensor)
    return db_sensor

def record_data(db: Session, mongodb_client: MongoDBClient, redis: Session, sensor_id: int, data: schemas.SensorData)-> schemas.Sensor:
    sensor = db.query(models.Sensor).filter(models.Sensor.id == sensor_id).first()
    data_json = convertToJSON(data)
    redis.set(sensor_id, data_json)
    doc_sensor = get_sensor_collection_by_name(name=sensor.name,mongodb_client=mongodb_client)
    db_sensor = schemas.Sensor(
        id = sensor.id,
        name = sensor.name,
        latitude = doc_sensor.latitude,
        longitude = doc_sensor.longitude,
        joined_at = str(sensor.joined_at),
        last_seen = data.last_seen,
        type= doc_sensor.type,
        mac_address= doc_sensor.mac_address,
        battery_level = data.battery_level,
        temperature = data.temperature,
        humidity = data.humidity,
        velocity = data.velocity
    )
    return db_sensor

def get_data(redis: Session, sensor_id: int, db: Session, mongodb_client: MongoDBClient) -> schemas.Sensor:
    sensor = db.query(models.Sensor).filter(models.Sensor.id == sensor_id).first()
    data_json = redis.get(sensor_id)
    data = convertToLastData(data_json)
    doc_sensor = get_sensor_collection_by_name(name=sensor.name,mongodb_client=mongodb_client)
    db_sensor = schemas.Sensor(
        id = sensor.id,
        name = sensor.name,
        latitude = doc_sensor.latitude,
        longitude = doc_sensor.longitude,
        joined_at = str(sensor.joined_at),
        last_seen = data.last_seen,
        type= doc_sensor.type,
        mac_address= doc_sensor.mac_address,
        battery_level = data.battery_level,
        temperature = data.temperature,
        humidity = data.humidity,
        velocity = data.velocity
    )
    return db_sensor

def delete_sensor(redis: Session, sensor_id: int, db: Session, mongodb_client: MongoDBClient):
    db_sensor = db.query(models.Sensor).filter(models.Sensor.id == sensor_id).first()
    name = db_sensor.name
    if db_sensor is None:
        raise HTTPException(status_code=404, detail="Sensor not found")
    db.delete(db_sensor)
    db.commit()
    delete_sensor_collection_by_name(name=name,mongodb_client=mongodb_client)
    redis.delete(sensor_id)
    return db_sensor

def convertToJSON(value):
    return json.dumps({
        'velocity': value.velocity,
        'temperature': value.temperature,
        'humidity': value.humidity,
        'battery_level': value.battery_level,
        'last_seen': value.last_seen
    })

def convertToLastData(value):
    data = json.loads(value)
    return schemas.SensorData(
        velocity=data['velocity'],
        temperature=data['temperature'],
        humidity=data['humidity'],
        battery_level=data['battery_level'],
        last_seen=data['last_seen']
    )

def add_collection(mongodb_client: MongoDBClient,sensor: schemas.SensorCreate) :
    mycol = mongodb_client.getCollection(collection='sensors_col')
    mycol.create_index([("location", "2dsphere")])
    sensor = {'name': sensor.name,
              'type': sensor.type, 
              'location': {
                    'type': "Point",
                    'coordinates': [sensor.longitude, sensor.latitude]
                },
              'mac_address': sensor.mac_address,
              'manufacturer': sensor.manufacturer,
              'model': sensor.model,
              'serie_number': sensor.serie_number,
              'firmware_version': sensor.firmware_version}
    mycol.insert_one(sensor)

def get_sensor_collection_by_name(name: str,mongodb_client: MongoDBClient) -> schemas.SensorCreate:
    mycol = mongodb_client.getCollection(collection='sensors_col')
    col_sensor = mycol.find_one({'name': name})
    
    return schemas.SensorCreate(name=name,
                                      type=col_sensor['type'],
                                      longitude=col_sensor['location']['coordinates'][0],
                                      latitude=col_sensor['location']['coordinates'][1],
                                      mac_address=col_sensor['mac_address'],
                                      manufacturer=col_sensor['manufacturer'],
                                      model=col_sensor['model'],
                                      serie_number=col_sensor['serie_number'],
                                      firmware_version=col_sensor['firmware_version'])

def delete_sensor_collection_by_name(name: str,mongodb_client: MongoDBClient):
    mycol = mongodb_client.getCollection(collection='sensors_col')
    mycol.delete_one({'name': name})

def get_sensors_near(db: Session, mongodb_client: MongoDBClient, redis: Session, latitude: float, longitude: float, radius: float):
    mycol = mongodb_client.getCollection(collection='sensors_col')
    query = mycol.find({
        "location": {
            "$near": {
                "$geometry": {
                    "type": "Point",
                    "coordinates": [longitude,latitude]
                },
                "$maxDistance": radius  
            }
        }
    })
    query_data = []
    
    for col in query:
        id = db.query(models.Sensor).filter(models.Sensor.name == col['name']).first().id
        query_data.append(get_data(redis=redis, sensor_id=id, db=db, mongodb_client=mongodb_client))

    return query_data
