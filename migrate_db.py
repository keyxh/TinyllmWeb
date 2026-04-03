import pymysql

connection = pymysql.connect(
    host='127.0.0.1',
    user='root',
    password='root',
    database='tinyllm'
)

try:
    cursor = connection.cursor()
    
    cursor.execute('ALTER TABLE devices ADD COLUMN mode VARCHAR(20) DEFAULT "normal"')
    print('添加 mode 字段成功')
    
    cursor.execute('ALTER TABLE devices ADD COLUMN frp_server VARCHAR(100) DEFAULT NULL')
    print('添加 frp_server 字段成功')
    
    connection.commit()
    print('数据库迁移完成')
    
except Exception as e:
    print(f'错误: {e}')
    connection.rollback()
finally:
    connection.close()
