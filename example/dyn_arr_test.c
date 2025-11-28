#include <assert.h>

#include "dyn_array.h"

int main() {
    array_t *arr = arr_create(1, sizeof(int));
    int a = 10;
    int b = 20;
    int c = 30;
    arr_push(arr, &a);
    arr_push(arr, &b);
    arr_push(arr, &c);
    //assert(c == *(int *)arr_pop(arr));
    assert(b == *(int *)arr_pop(arr));
    assert(a == *(int *)arr_pop(arr));
}
