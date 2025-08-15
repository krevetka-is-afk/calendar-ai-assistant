"""
Страница анализа календаря
"""
import streamlit as st

from app.core.config import NAVIGATION
from app.core.state_manager import StateManager
from app.core.calendar_utils import GoogleCalendarService, process_events_for_analysis
from app.core.ai_utils import get_ai_assistant
from app.core.ui_components import (
    render_authorization_status, render_calendar_selector,
    render_heatmap, render_events_table, render_weekly_timetable_plotly,
    render_loading_spinner, render_error_message, render_warning_message,
    render_info_message
)


def render_analytics_page():
    """Рендер страницы анализа календаря"""
    st.header("📊 Анализ календаря")
    
    # Проверка авторизации
    is_authorized = StateManager.is_authorized()
    render_authorization_status(is_authorized)
    
    if not is_authorized:
        st.warning("⚠️ Сначала авторизуйтесь в Google Calendar")
        
        # Кнопка авторизации
        if st.button("🔐 Войти через Google"):
            try:
                with render_loading_spinner("🔐 Авторизация через Google..."):
                    calendar_service = GoogleCalendarService()
                    service = calendar_service.get_service()
                    
                    if service:
                        StateManager.set_service(service)
                        StateManager.set_authorized(True)
                        
                        # Получение email пользователя
                        user_email = calendar_service.get_user_email(service)
                        StateManager.set_user_email(user_email)
                        
                        st.success("✅ Авторизация успешна!")
                        st.rerun()
                    else:
                        render_error_message("Не удалось получить сервис Google Calendar")
                        
            except Exception as e:
                render_error_message(f"Ошибка авторизации: {str(e)}")
        return
    
    # Получение сервиса и календарей
    service = StateManager.get_service()
    calendar_service = GoogleCalendarService()
    
    try:
        calendars = calendar_service.get_calendars(service)
        
        # Выбор календарей для анализа
        selected_calendars = render_calendar_selector(calendars)
        
        if selected_calendars:
            # Импорт событий
            if st.button("📥 Импортировать события"):
                try:
                    with render_loading_spinner("📥 Загрузка событий..."):
                        # Фильтруем календари по выбранным
                        filtered_calendars = {name: cal_id for name, cal_id in calendars.items() 
                                           if name in selected_calendars}
                        
                        user_email = StateManager.get_user_email()
                        events_data = calendar_service.fetch_events(service, filtered_calendars, user_email)
                        
                        st.success(f"✅ Загружено {len(events_data[0]['events'])} событий")
                        st.rerun()
                        
                except Exception as e:
                    render_error_message(f"Ошибка загрузки событий: {str(e)}")
            
            # Анализ загруженного файла
            data = None
            try:
                data = calendar_service.load_events_data()
            except Exception as e:
                render_error_message(f"Ошибка чтения данных: {str(e)}")
                data = None

            if data is None:
                render_info_message("Нет данных для анализа. Сначала импортируйте события из календаря.")
            else:
                events = data[0]["events"]
                
                if not events:
                    render_info_message("Нет событий для анализа. Сначала импортируйте события из календаря.")
                else:
                    # Обработка событий для анализа
                    df = process_events_for_analysis(events)
                    
                    # Выбор календарей для отображения
                    available_cals = sorted(df["calendar"].unique())
                    selected_calendars_display = st.multiselect(
                        "📊 Выберите календари для отображения:", 
                        available_cals,
                        default=available_cals
                    )

                    if selected_calendars_display:
                        df_selected = df[df["calendar"].isin(selected_calendars_display)]

                        # Подсчёт частотности по дням недели и часам для timetable/сетки
                        weekday_hour_counts = {}
                        for _, row in df_selected.iterrows():
                            key = (row["weekday"], row["hour"])
                            weekday_hour_counts[key] = weekday_hour_counts.get(key, 0) + 1

                        viz_options = ["Heatmap", "Timetable", "Bar Chart"]
                        choice = st.radio("🔍 Выберите тип визуализации:", viz_options, index=1)

                        if choice == "Heatmap":
                            st.subheader("🔥 Тепловая карта активности")
                            heatmap_data = df_selected.groupby(["weekday", "hour"])["duration_min"].sum().unstack(fill_value=0)
                            render_heatmap(heatmap_data)
                        elif choice == "Timetable":
                            st.subheader("📅 Таблица занятости по часам (неделя)")

                            # weekday_hour_counts = {}
                            # for _, row in df_selected.iterrows():
                            #     key = (row['weekday'], row['hour'])
                            #     weekday_hour_counts[key] = weekday_hour_counts.get(key, 0) + 1
                            render_weekly_timetable_plotly(weekday_hour_counts)
                        else:
                            st.subheader("📊 Количество событий по дням недели")
                            counts = df_selected['weekday'].value_counts().reindex(range(7), fill_value=0)
                            counts.index = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
                            st.bar_chart(counts)

                        # # Подсчёт частотности для timetable
                        # weekday_hour_counts = {}
                        # for _, row in df_selected.iterrows():
                        #     key = (row['weekday'], row['hour'])
                        #     weekday_hour_counts[key] = weekday_hour_counts.get(key, 0) + 1
                        #
                        # st.subheader("📅 Календарная сетка активности (экспериментально)")
                        # render_weekly_timetable_plotly(weekday_hour_counts)

                        if choice != "Timetable":
                            st.subheader("📅 Календарная сетка активности (экспериментально)")
                            render_weekly_timetable_plotly(weekday_hour_counts)

                        # Статистика
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Всего событий", len(df_selected))
                        with col2:
                            st.metric("Средняя продолжительность", f"{df_selected['duration_min'].mean():.1f} мин")
                        with col3:
                            if not df_selected.empty:
                                day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
                                most_busy_day = int(df_selected['weekday'].value_counts().idxmax())
                                st.metric("Самый загруженный день", day_names[most_busy_day])
                            else:
                                st.metric("Самый загруженный день", "Н/Д")

                        # Таблица событий
                        render_events_table(df_selected)
                        
                        # AI анализ
                        st.subheader("🤖 AI Анализ")
                        ai_assistant = get_ai_assistant()
                        
                        # Создание векторного хранилища
                        try:
                            ai_assistant.create_vector_store(events)
                            st.success("✅ Векторное хранилище создано для семантического поиска")
                        except Exception as e:
                            render_warning_message(f"Не удалось создать векторное хранилище: {str(e)}")
        
    except Exception as e:
        render_error_message(f"Ошибка получения календарей: {str(e)}")
