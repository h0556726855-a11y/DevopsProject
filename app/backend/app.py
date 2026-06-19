from flask import Flask, jsonify, request
import psycopg2
import os

app = Flask(__name__)


def get_db():
    return psycopg2.connect(
        host=os.environ['DB_HOST'],
        database=os.environ['DB_NAME'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD']
    )


@app.route('/health')
def health():
    return jsonify({'status': 'ok'})


@app.route('/products', methods=['GET'])
def get_products():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT id, name, price FROM products ORDER BY id')
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([{'id': r[0], 'name': r[1], 'price': float(r[2])} for r in rows])


@app.route('/products', methods=['POST'])
def add_product():
    data = request.get_json()
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO products (name, price) VALUES (%s, %s) RETURNING id',
        (data['name'], data['price'])
    )
    product_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'id': product_id, 'name': data['name'], 'price': data['price']}), 201


@app.route('/products/<int:product_id>', methods=['DELETE'])
def delete_product(product_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM products WHERE id = %s', (product_id,))
    conn.commit()
    cur.close()
    conn.close()
    return '', 204


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
