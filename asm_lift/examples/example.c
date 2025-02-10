#include <stdio.h>

/**
 * Add more functions to test different control flow statements ang CFGs.
 * 
 */

int switch_case_test(int num){
    switch(num){
        case 1:
            return 1;
        case 2:
            return 2;
        case 6:
            return 3;
        default:
            return 0;
    }
}

int multiple_nested_if_else_test(int num){
    if(num == 1){
        if(num == 2){
            if(num == 3){
                return 3;
            }
            else{
                return 2;
            }
        }
        else{
            return 1;
        }
    }
    else{
        return 0;
    }
}

int if_else_test(int num){
    if(num == 1){
        return 1;
    }
    else if(num == 2){
        return 2;
    }
    else if(num == 3){
        return 3;
    }
    else{
        return 0;
    }
}

int for_loop_test(int num){
    int sum = 0;
    for(int i = 0; i < num; i++){
        sum += i;
    }
    return sum;
}

int while_loop_test(int num){
    int sum = 0;
    while(num > 0){
        sum += num;
        num--;
    }
    return sum;
}

int do_while_loop_test(int num){
    int sum = 0;
    do{
        sum += num;
        num--;
    }while(num > 0);
    return sum;
}

int while_continue_break_test(int num){
    int sum = 0;
    while(num > 0){
        if(num == 3){
            num--;
            continue;
        }
        if(num == 1){
            break;
        }
        sum += num;
        num--;
    }
    return sum;
}

int function_pointer_call_test(int num, int val){
    int (*func[])(int) = {switch_case_test, multiple_nested_if_else_test, if_else_test, for_loop_test, while_loop_test, do_while_loop_test, while_continue_break_test};
    return func[val](num);
}

int main(){
    int num, val;
    scanf("%d %d", &num, &val);
    printf("%d\n", function_pointer_call_test(num, val));
    return 0;
}