#include <string.h>
#include <stdlib.h>

#include "dyn_array.h"

struct dynamic_array {
    int capacity;
    int size;
    int element_size;
    void *data;
};

array_t *arr_create(int initial_elements, int element_size) {
    array_t *a = malloc(sizeof(array_t));
    if(!a) return NULL;
    a->data = malloc(initial_elements * element_size);
    if(!a->data) {
        free(a);
        return NULL;
    }
    a->capacity = initial_elements;
    a->size = 0;
    a->element_size = element_size;
    return a;
}

int arr_push(array_t *arr, void *element) {
    if(arr->capacity < arr->size + 1) {
        void *temp = arr->data;
        arr->data = malloc(arr->size * arr->element_size * 2);
        if(!arr->data) return -1;
        arr->capacity *= 2;
        memcpy(arr->data, temp, arr->size * arr->element_size);
        free(temp);
    }
    memcpy((arr->data + (arr->size * arr->element_size)), element, arr->element_size);
    arr->size += 1;
    return arr->size - 1;
}

void *arr_pop(array_t *arr) {
    arr->size -= 1;
    return (arr->data + (arr->size * arr->element_size));
}
