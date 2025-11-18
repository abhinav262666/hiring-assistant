from mongoengine import Document, StringField


class User(Document):
    name = StringField()
    email = StringField()


print(dir(User._fields))


sample_user = User(name="abc", email="abcd")
print(type(sample_user._get_collection_name()))
