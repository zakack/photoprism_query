import requests
import argparse
import os

HOST = os.environ.get('PHOTOPRISM_HOST', 'http://127.0.0.1:2342')
USER = os.environ.get('PHOTOPRISM_USER', 'admin')
PASS = os.environ.get('PHOTOPRISM_PASS', 'admin')
SESSION_ID = os.environ.get('PHOTOPRISM_SESSION_ID', None)
DB_HOST = os.environ.get('PHOTOPRISM_DB_HOST', '127.0.0.1')
DB_PORT = int(os.environ.get('PHOTOPRISM_DB_PORT', 3306))
DB_USER = os.environ.get('PHOTOPRISM_DB_USER', 'photoprism')
DB_PASS = os.environ.get('PHOTOPRISM_DB_PASS', 'changeme')
DB_NAME = os.environ.get('PHOTOPRISM_DB_NAME', 'photoprism')


def get_albums(headers):
    response = requests.get(HOST + '/api/v1/albums?count=300', headers=headers)
    return response

def login(**kwargs):
    response = requests.post(HOST + '/api/v1/login', json=kwargs)
    return response

def keyword_exists(keyword, **db_kwargs):
    import pymysql
    db = pymysql.connect(**db_kwargs)
    cursor = db.cursor()
    cursor.execute("SELECT id FROM keywords WHERE keyword = %s", keyword)
    result = cursor.fetchone()
    #print("Found keyword: " + str(result[0]))
    db.close()
    return result

def search_photos(include_keywords, exclude_keywords, **db_kwargs):
    import pymysql
    db = pymysql.connect(**db_kwargs)
    cursor = db.cursor()

    # Prepare placeholders for the parameterized statement. One placeholder for each keyword ID.
    include_placeholders = ', '.join(['%s'] * len(include_keywords))
    exclude_placeholders = ', '.join(['%s'] * len(exclude_keywords))

    # Prepare the SQL statement with placeholders for parameterized queries.
    photo_query = f"""
    SELECT DISTINCT pk.photo_id
    FROM photos_keywords pk
    WHERE pk.keyword_id IN ({include_placeholders})
    AND NOT EXISTS (
        SELECT 1 FROM photos_keywords pk2
        WHERE pk2.photo_id = pk.photo_id
        AND pk2.keyword_id IN ({exclude_placeholders})
    )
    GROUP BY pk.photo_id
    HAVING COUNT(DISTINCT pk.keyword_id) = %s
    """
    uuid_query = f"SELECT photo_uid FROM photos WHERE id IN ({photo_query})"
    # Execute the query with the list of included and excluded keyword IDs.
    cursor.execute(uuid_query, (*include_keywords, *exclude_keywords, len(include_keywords)))

    # Fetch all results.
    results = [result[0].decode() for result in cursor.fetchall()]
    #print(results)

    db.close()
    return results

def get_keyword_ids(keywords, **db_kwargs):
    keyword_ids = []
    for keyword in keywords.split(','):
        keyword_id = keyword_exists(keyword, **db_kwargs)
        if not keyword_id:
            raise ValueError("Keyword not found: " + keyword)
        keyword_ids.append(keyword_id[0])
    return keyword_ids

def main():
    argparser = argparse.ArgumentParser()
    argparser.add_argument('--album', help='Album name')
    argparser.add_argument('--keywords', help='Keywords')
    argparser.add_argument('--exclude', help='Exclude keywords')
    args = argparser.parse_args()

    login_data = {'username': USER, 'password': PASS}

    album_id = None
    headers = {'X-Session-Id': SESSION_ID}
    albums = get_albums(headers)
    if albums.status_code != 200:
        print('Error retrieving albums')
        exit(1)
    for album in albums.json():
        if album['Title'] != args.album:
            continue
        album_id = album['UID']
    if not album_id:
        album = requests.post(HOST + '/api/v1/albums', headers=headers, json={'Title': args.album, 'Description': str(args.keywords)})
        album_id = album.json()['UID']
        print('Album not found, creating')

    db_kwargs = {'host': DB_HOST, 'port': DB_PORT, 'user': DB_USER, 'password': DB_PASS, 'db': DB_NAME}
    include_keywords = get_keyword_ids(args.keywords, **db_kwargs)
    exclude_keywords = get_keyword_ids(args.exclude, **db_kwargs)
    photos = search_photos(include_keywords, exclude_keywords, **db_kwargs)
    if photos:
        print(f'Found {len(photos)} photos')
        album_response = requests.post(HOST + '/api/v1/albums/' + album_id + '/photos', headers=headers, json={'photos': photos})
        if album_response.status_code != 200:
            print('Error adding photos to album')
            exit(1)
        else:
            print('Photos added to album.')
    else:
        print('No photos found')

if __name__ == '__main__':
    main()
