typedef struct dynamic_array array_t;

array_t *arr_create(int initial_elements, int element_size);
int arr_push(array_t *arr, void *element);
void *arr_pop(array_t *arr);
