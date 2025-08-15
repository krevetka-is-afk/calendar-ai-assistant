import React, {useState, useEffect} from 'react';
import {Calendar, Clock, Upload, ChevronRight, X, Loader2, BarChart3, Target, Zap} from 'lucide-react';

const API_BASE = '/api/v1';

const SmartCalendarSidebar = () => {
    const [file, setFile] = useState(null);
    const [loading, setLoading] = useState(false);
    const [activeTab, setActiveTab] = useState('schedule');
    const [eventQuery, setEventQuery] = useState({
        summary: '',
        duration_min: 60,
        priority_type: 'regular'
    });
    const [recommendation, setRecommendation] = useState(null);
    const [importStats, setImportStats] = useState(null);
    const [cacheKey, setCacheKey] = useState(null);
    const [analytics, setAnalytics] = useState(null);

    const typeColors = {
        'работа': 'bg-blue-500',
        'учёба_и_саморазвитие': 'bg-purple-500',
        'здоровье_и_активность': 'bg-green-500',
        'семья_и_отношения': 'bg-pink-500',
        'отдых_и_досуг': 'bg-yellow-500',
        'прочее': 'bg-slate-400'
    };

    const calculatePatternCount = (patterns) => {
        if (!patterns) return 0;
        return Object.values(patterns).reduce((total, value) => {
            if (Array.isArray(value)) {
                return total + value.length;
            }
            if (value && typeof value === 'object') {
                return total + Object.keys(value).length;
            }
            return total;
        }, 0);
    };

    const formatTime = (isoString) => {
        const date = new Date(isoString);
        return date.toLocaleTimeString('ru-RU', {
            hour: '2-digit',
            minute: '2-digit'
        });
    };

    const formatDate = (isoString) => {
        const date = new Date(isoString);
        const days = ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'];
        const months = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
        return `${days[date.getDay()]}, ${date.getDate()} ${months[date.getMonth()]}`;
    };

    const handleFileUpload = (e) => {
        const uploadedFile = e.target.files[0];
        if (uploadedFile && uploadedFile.name.endsWith('.ics')) {
            setFile(uploadedFile);
        }
    };

    const processCalendar = async () => {
        if (!file || !eventQuery.summary) return;

        setLoading(true);
        const formData = new FormData();
        formData.append('file', file);
        formData.append('timezone', 'Europe/Moscow');
        formData.append('expand_recurring', 'true');
        formData.append('horizon_days', '30');
        formData.append('days_limit', '14');

        try {
            const flowResponse = await fetch(`${API_BASE}/flow/import+enrich+analyze`, {
                method: 'POST',
                body: formData
            });

            const flowData = await flowResponse.json();

            if (flowResponse.ok) {
                setCacheKey(flowData.cache_key);
                setAnalytics(flowData.analysis);
                setImportStats({
                    totalEvents: flowData.analysis?.dashboard_aggregates?.total_events,
                    analyzed: flowData.analysis?.dashboard_aggregates?.meetings_hours,
                    patterns: flowData.analysis ? calculatePatternCount(flowData.analysis.patterns) : 0,
                });

                const queryData = new FormData();
                queryData.append('summary', eventQuery.summary);
                queryData.append('duration_min', eventQuery.duration_min);
                queryData.append('priority_type', eventQuery.priority_type);
                queryData.append('cache_key', flowData.cache_key);

                const recResponse = await fetch(`${API_BASE}/flow/user_query+recommendation`, {
                    method: 'POST',
                    body: queryData
                });

                const recData = await recResponse.json();
                if (recResponse.ok) {
                    setRecommendation(recData);
                    setActiveTab('recommendation');
                } else {
                    console.error(recData);
                }
            } else {
                console.error(flowData);
            }
        } catch (err) {
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        const fetchAnalytics = async () => {
            if (activeTab === 'analytics' && cacheKey) {
                try {
                    const response = await fetch(`${API_BASE}/flow/analytics?cache_key=${cacheKey}`);
                    const data = await response.json();
                    if (response.ok) {
                        setAnalytics(data);
                        setImportStats({
                            totalEvents: data.dashboard_aggregates?.total_events,
                            analyzed: data.dashboard_aggregates?.meetings_hours,
                            patterns: data.patterns ? calculatePatternCount(data.patterns) : 0,
                        });
                    } else {
                        console.error(data);
                    }
                } catch (err) {
                    console.error(err);
                }
            }
        };
        fetchAnalytics();
    }, [activeTab, cacheKey]);

    const tabs = [
        {id: 'schedule', label: 'Планирование', icon: Calendar},
        {id: 'recommendation', label: 'Рекомендация', icon: Target},
        {id: 'analytics', label: 'Аналитика', icon: BarChart3}
    ];

    return (
        <div className="flex h-screen bg-slate-50">
            {/* Sidebar */}
            <div className="w-80 bg-white border-r border-slate-200">
                <div className="p-6 border-b border-slate-100">
                    <div className="flex items-center space-x-3">
                        <div
                            className="w-10 h-10 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-xl flex items-center justify-center">
                            <Calendar className="w-5 h-5 text-white"/>
                        </div>
                        <div>
                            <h1 className="text-lg font-semibold text-slate-900">Smart Calendar</h1>
                            <p className="text-xs text-slate-500">AI-powered scheduling</p>
                        </div>
                    </div>
                </div>

                {/* File Upload Section */}
                <div className="p-6 border-b border-slate-100">
                    <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                        Календарь
                    </label>
                    <div className="mt-3">
                        <input
                            type="file"
                            accept=".ics"
                            onChange={handleFileUpload}
                            className="hidden"
                            id="file-upload"
                        />
                        <label
                            htmlFor="file-upload"
                            className="flex items-center justify-center w-full py-3 px-4 border-2 border-dashed border-slate-200 rounded-lg cursor-pointer hover:border-indigo-300 hover:bg-indigo-50 transition-colors"
                        >
                            <Upload className="w-4 h-4 text-slate-400 mr-2"/>
                            <span className="text-sm text-slate-600">
                {file ? file.name.substring(0, 20) + '...' : 'Загрузить .ics'}
              </span>
                        </label>
                    </div>
                    {file && (
                        <div
                            className="mt-2 flex items-center justify-between text-xs text-green-600 bg-green-50 px-3 py-2 rounded-lg">
                            <span>Файл загружен</span>
                            <button onClick={() => setFile(null)}>
                                <X className="w-3 h-3"/>
                            </button>
                        </div>
                    )}
                </div>

                {/* Event Query Form */}
                <div className="p-6 space-y-4">
                    <div>
                        <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                            Новое событие
                        </label>
                        <input
                            type="text"
                            value={eventQuery.summary}
                            onChange={(e) => setEventQuery({...eventQuery, summary: e.target.value})}
                            placeholder="Название события"
                            className="mt-2 w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none"
                        />
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <label className="text-xs text-slate-500">Длительность</label>
                            <select
                                value={eventQuery.duration_min}
                                onChange={(e) => setEventQuery({...eventQuery, duration_min: parseInt(e.target.value)})}
                                className="mt-1 w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
                            >
                                <option value="30">30 мин</option>
                                <option value="60">1 час</option>
                                <option value="90">1.5 часа</option>
                                <option value="120">2 часа</option>
                            </select>
                        </div>
                        <div>
                            <label className="text-xs text-slate-500">Приоритет</label>
                            <select
                                value={eventQuery.priority_type}
                                onChange={(e) => setEventQuery({...eventQuery, priority_type: e.target.value})}
                                className="mt-1 w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
                            >
                                <option value="regular">Обычный</option>
                                <option value="high">Высокий</option>
                            </select>
                        </div>
                    </div>

                    <button
                        onClick={processCalendar}
                        disabled={!file || !eventQuery.summary || loading}
                        className="w-full py-2.5 bg-gradient-to-r from-indigo-500 to-purple-600 text-white rounded-lg text-sm font-medium hover:shadow-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center"
                    >
                        {loading ? (
                            <>
                                <Loader2 className="w-4 h-4 mr-2 animate-spin"/>
                                Анализ...
                            </>
                        ) : (
                            <>
                                <Zap className="w-4 h-4 mr-2"/>
                                Найти время
                            </>
                        )}
                    </button>
                </div>

                {/* Navigation Tabs */}
                <div className="mt-auto border-t border-slate-100">
                    <nav className="p-3 space-y-1">
                        {tabs.map(tab => (
                            <button
                                key={tab.id}
                                onClick={() => setActiveTab(tab.id)}
                                className={`w-full flex items-center space-x-3 px-3 py-2 rounded-lg transition-colors ${
                                    activeTab === tab.id
                                        ? 'bg-indigo-50 text-indigo-600'
                                        : 'text-slate-600 hover:bg-slate-50'
                                }`}
                            >
                                <tab.icon className="w-4 h-4"/>
                                <span className="text-sm font-medium">{tab.label}</span>
                            </button>
                        ))}
                    </nav>
                </div>
            </div>

            {/* Main Content */}
            <div className="flex-1 overflow-auto">
                {activeTab === 'schedule' && (
                    <div className="p-8">
                        <div className="max-w-4xl mx-auto">
                            <h2 className="text-2xl font-light text-slate-900 mb-6">Планирование события</h2>

                            <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-8">
                                <div className="grid grid-cols-3 gap-8">
                                    <div className="text-center">
                                        <div
                                            className="w-12 h-12 bg-indigo-100 rounded-full flex items-center justify-center mx-auto mb-3">
                                            <Upload className="w-6 h-6 text-indigo-600"/>
                                        </div>
                                        <h3 className="font-medium text-slate-900 mb-1">Загрузите календарь</h3>
                                        <p className="text-sm text-slate-500">Импортируйте .ics файл</p>
                                    </div>

                                    <div className="text-center">
                                        <div
                                            className="w-12 h-12 bg-purple-100 rounded-full flex items-center justify-center mx-auto mb-3">
                                            <Clock className="w-6 h-6 text-purple-600"/>
                                        </div>
                                        <h3 className="font-medium text-slate-900 mb-1">Укажите параметры</h3>
                                        <p className="text-sm text-slate-500">Название и длительность</p>
                                    </div>

                                    <div className="text-center">
                                        <div
                                            className="w-12 h-12 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-3">
                                            <Target className="w-6 h-6 text-green-600"/>
                                        </div>
                                        <h3 className="font-medium text-slate-900 mb-1">Получите рекомендацию</h3>
                                        <p className="text-sm text-slate-500">AI найдет лучшее время</p>
                                    </div>
                                </div>

                                <div className="mt-8 p-6 bg-slate-50 rounded-xl">
                                    <h4 className="text-sm font-medium text-slate-700 mb-3">Как это работает</h4>
                                    <ul className="space-y-2 text-sm text-slate-600">
                                        <li className="flex items-start">
                                            <span
                                                className="inline-block w-1.5 h-1.5 rounded-full bg-slate-400 mt-1.5 mr-2 flex-shrink-0"></span>
                                            Система анализирует ваш календарь за последние 2 недели
                                        </li>
                                        <li className="flex items-start">
                                            <span
                                                className="inline-block w-1.5 h-1.5 rounded-full bg-slate-400 mt-1.5 mr-2 flex-shrink-0"></span>
                                            Определяет паттерны и предпочтения по времени
                                        </li>
                                        <li className="flex items-start">
                                            <span
                                                className="inline-block w-1.5 h-1.5 rounded-full bg-slate-400 mt-1.5 mr-2 flex-shrink-0"></span>
                                            Находит оптимальный слот с учетом типа события
                                        </li>
                                    </ul>
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {activeTab === 'recommendation' && recommendation && (
                    <div className="p-8">
                        <div className="max-w-4xl mx-auto">
                            <h2 className="text-2xl font-light text-slate-900 mb-6">Рекомендованное время</h2>

                            {/* Main Recommendation Card */}
                            <div
                                className="bg-gradient-to-br from-indigo-500 to-purple-600 rounded-2xl p-8 text-white mb-6">
                                <div className="flex items-start justify-between mb-6">
                                    <div>
                                        <h3 className="text-xl font-medium mb-2">{eventQuery.summary}</h3>
                                        <p className="text-indigo-100">Длительность: {eventQuery.duration_min} минут</p>
                                    </div>
                                    <div className="text-right">
                                        <div className="text-3xl font-light">
                                            {Math.round(recommendation.recommendation.score * 100)}%
                                        </div>
                                        <div className="text-xs text-indigo-200 mt-1">соответствие</div>
                                    </div>
                                </div>

                                <div className="bg-white/10 rounded-xl p-6 backdrop-blur">
                                    <div className="flex items-center justify-between mb-4">
                                        <div>
                                            <div className="text-2xl font-light">
                                                {formatDate(recommendation.recommendation.slot.start)}
                                            </div>
                                            <div className="text-indigo-200 mt-1">
                                                {formatTime(recommendation.recommendation.slot.start)} — {formatTime(recommendation.recommendation.slot.end)}
                                            </div>
                                        </div>
                                        <Clock className="w-8 h-8 text-indigo-200"/>
                                    </div>

                                    {recommendation.recommendation.rationale && (
                                        <div className="mt-4 pt-4 border-t border-white/20 space-y-2">
                                            {recommendation.recommendation.rationale.slice(0, 3).map((reason, idx) => (
                                                <div key={idx} className="flex items-start text-sm">
                                                    <ChevronRight className="w-3 h-3 mt-0.5 mr-2 flex-shrink-0"/>
                                                    <span>{reason}</span>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            </div>

                            {/* Alternative Options */}
                            {recommendation.alternatives && recommendation.alternatives.length > 0 && (
                                <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
                                    <h4 className="text-sm font-semibold text-slate-700 mb-4">Альтернативные
                                        варианты</h4>
                                    <div className="space-y-3">
                                        {recommendation.alternatives.map((alt, idx) => (
                                            <div key={idx}
                                                 className="flex items-center justify-between p-4 bg-slate-50 rounded-lg hover:bg-slate-100 transition-colors cursor-pointer">
                                                <div>
                                                    <div className="font-medium text-slate-900">
                                                        {formatDate(alt.slot.start)}
                                                    </div>
                                                    <div className="text-sm text-slate-500 mt-1">
                                                        {formatTime(alt.slot.start)} — {formatTime(alt.slot.end)}
                                                    </div>
                                                </div>
                                                <div className="text-right">
                                                    <div className="text-lg font-medium text-slate-700">
                                                        {Math.round(alt.score * 100)}%
                                                    </div>
                                                    <div className="text-xs text-slate-500">соответствие</div>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {activeTab === 'analytics' && analytics && (
                    <div className="p-8">
                        <div className="max-w-4xl mx-auto">
                            <h2 className="text-2xl font-light text-slate-900 mb-6">Аналитика календаря</h2>

                            <div className="grid grid-cols-3 gap-6 mb-6">
                                <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
                                    <div className="flex items-center justify-between mb-4">
                                        <div
                                            className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
                                            <Calendar className="w-5 h-5 text-blue-600"/>
                                        </div>
                                        <span className="text-xs text-slate-500">События</span>
                                    </div>
                                    <div className="text-3xl font-light text-slate-900">{importStats?.totalEvents}</div>
                                    <div className="text-sm text-slate-500 mt-1">импортировано</div>
                                </div>

                                <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
                                    <div className="flex items-center justify-between mb-4">
                                        <div
                                            className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center">
                                            <BarChart3 className="w-5 h-5 text-purple-600"/>
                                        </div>
                                        <span className="text-xs text-slate-500">Анализ</span>
                                    </div>
                                    <div className="text-3xl font-light text-slate-900">{importStats?.analyzed}</div>
                                    <div className="text-sm text-slate-500 mt-1">слотов проверено</div>
                                </div>

                                <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
                                    <div className="flex items-center justify-between mb-4">
                                        <div
                                            className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center">
                                            <Target className="w-5 h-5 text-green-600"/>
                                        </div>
                                        <span className="text-xs text-slate-500">Паттерны</span>
                                    </div>
                                    <div className="text-3xl font-light text-slate-900">{importStats?.patterns}</div>
                                    <div className="text-sm text-slate-500 mt-1">найдено</div>
                                </div>
                            </div>

                            <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
                                <h4 className="text-sm font-semibold text-slate-700 mb-4">Распределение по типам</h4>
                                <div className="space-y-3">
                                    {analytics.patterns?.time_distribution ? (
                                        Object.entries(analytics.patterns.time_distribution).map(([type, value]) => (
                                            <div key={type}>
                                                <div className="flex items-center justify-between text-sm mb-1">
                                                    <span className="text-slate-700">{type}</span>
                                                    <span className="text-slate-500">{value}%</span>
                                                </div>
                                                <div className="w-full bg-slate-100 rounded-full h-2">
                                                    <div
                                                        className={`${typeColors[type] || 'bg-indigo-500'} h-2 rounded-full transition-all duration-500`}
                                                        style={{width: `${value}%`}}
                                                    />
                                                </div>
                                            </div>
                                        ))
                                    ) : (
                                        <div className="text-sm text-slate-500">Нет данных</div>
                                    )}
                                </div>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default SmartCalendarSidebar;