async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_data = context.user_data
    state = user_data.get('state')
    text = update.message.text.strip()
    
    if state == 'esperando_monto_riesgo':
        await recibir_monto_riesgo(update, context)
    elif state in ['esperando_sl', 'esperando_tp']:
        await set_sl_tp(update, context)
    elif state in ['solicitud_deposito', 'solicitud_retiro']:
        await recibir_monto(update, context)
    elif state == 'solicitud_retiro_datos':
        await recibir_datos(update, context)
    elif 'rechazando_solicitud' in user_data:
        await receive_rejection_reason(update, context)
    elif 'awaiting_custom_leverage' in user_data:
        # Manejar apalancamiento personalizado
        try:
            leverage = float(text)
            if leverage <= 0:
                await update.message.reply_text("❌ El apalancamiento debe ser mayor a 0. Intenta nuevamente.")
                return
                
            custom_data = user_data['awaiting_custom_leverage']
            asset_id = custom_data['asset_id']
            currency = custom_data['currency']
            operation_type = custom_data['operation_type']
            
            await process_leverage_selection(update, context, asset_id, currency, operation_type, leverage)
            
            del user_data['awaiting_custom_leverage']
        except ValueError:
            await update.message.reply_text("❌ Por favor, envía un número válido para el apalancamiento.")
    elif 'modifying_sl' in user_data or 'modifying_tp' in user_data:
        try:
            value = float(text)
            if 'modifying_sl' in user_data:
                op_id = user_data['modifying_sl']
                supabase.table('operations').update({'sl_price': value}).eq('id', op_id).execute()
                await update.message.reply_text("✅ Stop Loss actualizado correctamente.")
                del user_data['modifying_sl']
            elif 'modifying_tp' in user_data:
                op_id = user_data['modifying_tp']
                supabase.table('operations').update({'tp_price': value}).eq('id', op_id).execute()
                await update.message.reply_text("✅ Take Profit actualizado correctamente.")
                del user_data['modifying_tp']
        except ValueError:
            await update.message.reply_text("❌ Por favor, envía un número válido.")
    else:
        await update.message.reply_text(
            "No entiendo ese comando. Usa /start para comenzar.",
            reply_markup=get_navigation_keyboard()
        )
