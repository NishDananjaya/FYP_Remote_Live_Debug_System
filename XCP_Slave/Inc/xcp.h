/*
 * xcp.h
 *
 *  Created on: May 20, 2025
 *      Author: Pathum Dissanayake
 */

#ifndef XCP_H
#define XCP_H

#include <stdint.h>
#include <stdbool.h>

extern volatile bool spi_busy;

/* XCP Command Packet Identifiers (PIDs) */
#define XCP_CONNECT     0xFF
#define XCP_DISCONNECT  0xFE
#define XCP_GET_STATUS  0xFD
#define XCP_SYNCH       0xFC
#define XCP_SET_MTA     0xF6
#define XCP_UPLOAD      0xF5
#define XCP_DOWNLOAD    0xF0

#define DUMMY_DATA      0xAA

/* XCP Response Packet Identifiers */
#define XCP_PID_RES     0xFF
#define XCP_PID_ERR     0xFE

/* Error Codes */
#define XCP_ERR_CMD_UNKNOWN  0x20
#define XCP_ERR_CMD_SYNTAX  0x21
#define XCP_ERR_OUT_OF_RANGE 0x22
#define XCP_ERR_CMD_BUSY    0x10

/* Buffer Sizes */
#define XCP_MAX_CTO    8
#define XCP_MAX_DTO    8

#define XCP_PROTOCOL_VERSION     0x01
#define XCP_TRANSPORT_VERSION    0x01

/* Memory Regions (STM32F407xx) */
#define FLASH_START     0x08000000
#define FLASH_SIZE      (1024*1024) // 1MB for STM32F407xx
#define RAM_START       0x20000000
#define RAM_SIZE        (128*1024)  // 128KB for STM32F407xx

/* Function Prototypes */
void XCP_CommandHandler(uint8_t *cmd, uint8_t *res);
void XCP_Task(void);
bool ValidateAddress(uint32_t addr);

extern volatile uint32_t mta_address;
extern volatile uint8_t mta_extension;

/* Command Handlers */
void XCP_Connect(uint8_t *cmd, uint8_t *res);
void XCP_Disconnect(uint8_t *cmd, uint8_t *res);
void XCP_GetStatus(uint8_t *cmd, uint8_t *res);
void XCP_Synch(uint8_t *cmd, uint8_t *res);
void XCP_SetMTA(uint8_t *cmd, uint8_t *res);
void XCP_Upload(uint8_t *cmd, uint8_t *res);
void XCP_Download(uint8_t *cmd, uint8_t *res);

#endif /* XCP_H */
