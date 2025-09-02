/*
 * spi.c
 *
 *  Created on: May 22, 2025
 *      Author: Pathum Dissanayake
 */

#include "spi.h"
#include "xcp.h"
#include "main.h"
#include <string.h>

SPI_HandleTypeDef hspi1;
DMA_HandleTypeDef hdma_spi1_rx;
DMA_HandleTypeDef hdma_spi1_tx;

uint8_t rxBuffer[SPI_BUFFER_SIZE];
uint8_t txBuffer[SPI_BUFFER_SIZE];



void SPI_Init(void)
{
    hspi1.Instance = SPI1;
    hspi1.Init.Mode = SPI_MODE_SLAVE;
    hspi1.Init.Direction = SPI_DIRECTION_2LINES;
    hspi1.Init.DataSize = SPI_DATASIZE_8BIT;
    hspi1.Init.CLKPolarity = SPI_POLARITY_LOW;
    hspi1.Init.CLKPhase = SPI_PHASE_1EDGE;
    hspi1.Init.NSS = SPI_NSS_SOFT;
    hspi1.Init.FirstBit = SPI_FIRSTBIT_MSB;
    hspi1.Init.TIMode = SPI_TIMODE_DISABLE;
    hspi1.Init.CRCCalculation = SPI_CRCCALCULATION_DISABLE;
    hspi1.Init.CRCPolynomial = 10;

    if (HAL_SPI_Init(&hspi1) != HAL_OK)
    {
        Error_Handler();
    }
}

void SPI_Start(void)
{
    memset(rxBuffer, 0, SPI_BUFFER_SIZE);
    memset(txBuffer, 0, SPI_BUFFER_SIZE);
    HAL_SPI_TransmitReceive_DMA(&hspi1, txBuffer, rxBuffer, SPI_BUFFER_SIZE);
}

void HAL_SPI_TxRxCpltCallback(SPI_HandleTypeDef *hspi)
{
    if (hspi == &hspi1)
    {

        HAL_GPIO_TogglePin(GPIOD, GPIO_PIN_15);
        XCP_CommandHandler(rxBuffer, txBuffer);
        memset(rxBuffer, 0, SPI_BUFFER_SIZE);
        HAL_SPI_TransmitReceive_DMA(&hspi1, txBuffer, rxBuffer, SPI_BUFFER_SIZE);
    }
}



