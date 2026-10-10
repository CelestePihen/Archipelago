#include <kamek.h>

//breakpoint 0x80c7fecf

// this makes level points red
kmBranchDefCpp(0x800fa440, 0x800fa6e4, int, int param_1, int param_2)
{
    return 2;
}

/*
kmBranchDefAsm(0x809061b0, 0x80906290)
{
    li r3, 1
    blr
}
*/

// this fixes so paths are walkable
kmBranchDefCpp(0x80906190,0x809062a8,int, int param_1, int param_2)
{
    return 1;
}


/*
kmBranchDefCpp(0x808e2380,0x808e2468,int, int param_1, int param_2)
{
    return 1;
}
*/

/*
kmBranchDefCpp(0x800fd9b0, 0x800faf88, bool, void)
{
    return true;
}

*/