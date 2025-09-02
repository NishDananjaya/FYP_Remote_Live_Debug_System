/**
******************************************************************************
XCP.c
For STM32 microcontrollers
Author: Pathum J Dissanayake
Created: May 20, 2025
******************************************************************************/

#include <string.h>
#include <stdbool.h>
#include "spi.h"
#include "xcp.h"

extern uint8_t rxBuffer[];
extern uint8_t txBuffer[];

volatile uint32_t mta_address = 0;
volatile uint8_t mta_extension = 0;


bool ValidateAddress(uint32_t addr) {
    if ((addr >= FLASH_START && addr < (FLASH_START + FLASH_SIZE)) ||
        (addr >= RAM_START && addr < (RAM_START + RAM_SIZE))) {
        return true;
    }
    return false;
}

void XCP_Connect(uint8_t *cmd, uint8_t *res) {
    memset(res, 0, XCP_MAX_DTO);  // Clear entire buffer
    res[0] = XCP_PID_RES;
    res[1] = 0x20;  // Resource: Calibration + Page Switching
    res[2] = XCP_MAX_CTO;
    res[3] = 0x00;  // Comm mode
    res[4] = XCP_MAX_DTO;
    res[5] = XCP_PROTOCOL_VERSION;
    res[6] = XCP_TRANSPORT_VERSION;

}

void XCP_Disconnect(uint8_t *cmd, uint8_t *res) {
	memset(res, 0, XCP_MAX_DTO);
    res[0] = XCP_PID_RES;
}

void XCP_GetStatus(uint8_t *cmd, uint8_t *res) {
    memset(res, 0, XCP_MAX_DTO);
    res[0] = XCP_PID_RES;
}

void XCP_Synch(uint8_t *cmd, uint8_t *res) {
    res[0] = XCP_PID_RES;
}

void XCP_SetMTA(uint8_t *cmd, uint8_t *res) {
	memset(res, 0, XCP_MAX_DTO);
    uint32_t addr = (uint32_t)cmd[4] |
                    ((uint32_t)cmd[5] << 8) |
                    ((uint32_t)cmd[6] << 16) |
                    ((uint32_t)cmd[7] << 24);


    if (!ValidateAddress(addr)) {
        res[0] = XCP_PID_ERR;
        res[1] = XCP_ERR_OUT_OF_RANGE;
        return;
    }

    mta_address = addr;
    res[0] = XCP_PID_RES;
}

void XCP_Upload(uint8_t *cmd, uint8_t *res) {
	memset(res, 0, XCP_MAX_DTO);
    uint8_t length = cmd[1];

    if (!ValidateAddress(mta_address) || (length > (XCP_MAX_DTO - 1))) {
        res[0] = XCP_PID_ERR;
        res[1] = XCP_ERR_OUT_OF_RANGE;
        return;
    }
    res[0] = XCP_PID_RES;
    __disable_irq();
    memcpy(&res[1], (uint8_t*)mta_address, length);
    __enable_irq();
    mta_address += length;

}

void XCP_Download(uint8_t *cmd, uint8_t *res) {
	memset(res, 0, XCP_MAX_DTO);
    uint8_t length = cmd[1];

    if (!ValidateAddress(mta_address) || (length > (XCP_MAX_CTO - 2))) {
        res[0] = XCP_PID_ERR;
        res[1] = XCP_ERR_OUT_OF_RANGE;
        return;
    }

    __disable_irq();
    memcpy((uint8_t*)mta_address, &cmd[2], length);
    mta_address += length;
    res[0] = XCP_PID_RES;
    __enable_irq();
}

void XCP_CommandHandler(uint8_t *cmd, uint8_t *res) {

    uint8_t pid = cmd[0];
    if (pid == 0xAA) {
        return;
    }

    switch (pid) {
        case XCP_CONNECT:    XCP_Connect(cmd, res);    break;
        case XCP_DISCONNECT: XCP_Disconnect(cmd, res); break;
        case XCP_GET_STATUS: XCP_GetStatus(cmd, res);  break;
        case XCP_SYNCH:      XCP_Synch(cmd, res);      break;
        case XCP_SET_MTA:    XCP_SetMTA(cmd, res);     break;
        case XCP_UPLOAD:     XCP_Upload(cmd, res);     break;
        case XCP_DOWNLOAD:   XCP_Download(cmd, res);   break;
        default:
            res[0] = XCP_PID_ERR;
            res[1] = XCP_ERR_CMD_UNKNOWN;
            break;
    }

}



