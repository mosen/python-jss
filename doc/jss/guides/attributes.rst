JSSObject Attributes
====================

If you need to expand on the list of objects supported by python-jss it may help to know the behaviour of the class
attributes.

All subclasses of **JSSObject** can have attributes which indicate which kinds of functionality are available on that
object.

Summary
-------

can_list
    Bool whether object allows a list GET request.

can_get
    Bool whether object allows a GET request.

can_put
    Bool whether object allows a PUT request.

can_post
    Bool whether object allows a POST request.

can_delete
    Bool whether object allows a DEL request.

id_url
    String URL piece to append to use the ID property for requests. (Usually ``"/id/"``)

container
    String pluralized object name. This is used in one place-Account and AccountGroup use the same API call.
    container is used to differentiate the results.

default_search
    String default search type to utilize for GET.

search_types
    Dict of search types available to object:

    - **Key:** Search type name. At least one must match the
      default_search.
    - **Val:** URL component to use to request via this search_type.

can_subset
    Bool Whether class allows subset arguments to GET
    queries.

list_type
    String singular form of object type found in containers (e.g. ComputerGroup has a container with tag:
    "computers" holding "computer" elements. The list_type is "computer").

data_keys
    Dictionary of keys to create if instantiating a
    blank object using the _new method.

    - **Keys:** String names of keys to create at top level.
    - **Vals:** Values to set for the key.

      Int and bool values get converted to string.

      Dicts are recursively added (so their keys are added to
      parent key, etc).

