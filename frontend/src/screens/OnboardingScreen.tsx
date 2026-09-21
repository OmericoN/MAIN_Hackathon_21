import { useState, type FormEvent } from 'react'
import { ArrowLeft, ArrowRight, Check, Flame, Leaf, Sparkles, Utensils } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { Button, Chip } from '../components/UI'
import { useAuth } from '../context/AuthContext'

const diets = ['vegan', 'vegetarian', 'no preference']
const allergens = ['gluten', 'nuts', 'milk', 'eggs', 'soybeans', 'shellfish']
const cuisines = ['italian', 'asian', 'mexican', 'mediterranean', 'indian', 'middle eastern']
const tastes = ['fresh', 'savory', 'spicy', 'comforting']

export function OnboardingScreen() {
  const { api } = useAuth(); const navigate = useNavigate()
  const [step, setStep] = useState(1)
  const [name, setName] = useState('Alex')
  const [diet, setDiet] = useState('vegetarian')
  const [selectedAllergies, setSelectedAllergies] = useState<string[]>([])
  const [selectedCuisines, setSelectedCuisines] = useState(['italian', 'mediterranean'])
  const [selectedTastes, setSelectedTastes] = useState(['fresh'])
  const [calories, setCalories] = useState(2000)
  const [saving, setSaving] = useState(false)
  const toggle = (list: string[], value: string, setter: (items: string[]) => void) => setter(list.includes(value) ? list.filter((item) => item !== value) : [...list, value])

  async function finish(event: FormEvent) {
    event.preventDefault(); setSaving(true)
    await api.completeOnboarding({ display_name: name, dietary_preferences: diet === 'no preference' ? [] : [diet], allergies: selectedAllergies, preferred_cuisines: selectedCuisines, preferred_tastes: selectedTastes, daily_calorie_target: calories })
    navigate('/')
  }

  return <form className="onboarding" onSubmit={finish}>
    <div className="onboarding__top"><button className="icon-button" type="button" onClick={() => step === 1 ? navigate('/auth') : setStep((value) => value - 1)}><ArrowLeft /></button><span>Step {step} of 3</span></div>
    <div className="progress"><i style={{ width: `${step / 3 * 100}%` }} /></div>
    <div className="onboarding__intro"><span className="feature-icon">{step === 1 ? <Leaf /> : step === 2 ? <Utensils /> : <Sparkles />}</span><h1>{step === 1 ? 'Let’s get to know you' : step === 2 ? 'What works for your body?' : 'Make every meal feel like yours'}</h1><p>{step === 1 ? 'A few details help us make plans that actually fit.' : step === 2 ? 'We will always protect your dietary choices.' : 'Choose the flavours you reach for most.'}</p></div>
    {step === 1 ? <div className="onboarding__body"><label className="field"><span>What should we call you?</span><input value={name} onChange={(event) => setName(event.target.value)} required /></label><div className="choice-block"><span><Leaf />Diet</span><div className="chip-grid">{diets.map((item) => <Chip key={item} selected={diet === item} onClick={() => setDiet(item)}>{diet === item ? <Check /> : null}{item}</Chip>)}</div></div></div> : null}
    {step === 2 ? <div className="onboarding__body"><div className="choice-block"><span>Allergies</span><small>Select every ingredient we should avoid.</small><div className="chip-grid">{allergens.map((item) => <Chip key={item} selected={selectedAllergies.includes(item)} onClick={() => toggle(selectedAllergies, item, setSelectedAllergies)}>{item}</Chip>)}</div></div><div className="choice-block"><span><Flame />Daily calorie target</span><div className="range-value">{calories.toLocaleString()} kcal</div><input className="range" type="range" min="1200" max="3200" step="100" value={calories} onChange={(event) => setCalories(Number(event.target.value))} /></div></div> : null}
    {step === 3 ? <div className="onboarding__body"><div className="choice-block"><span>Preferred cuisines</span><div className="chip-grid">{cuisines.map((item) => <Chip key={item} selected={selectedCuisines.includes(item)} onClick={() => toggle(selectedCuisines, item, setSelectedCuisines)}>{item}</Chip>)}</div></div><div className="choice-block"><span>Favourite tastes</span><div className="chip-grid">{tastes.map((item) => <Chip key={item} selected={selectedTastes.includes(item)} onClick={() => toggle(selectedTastes, item, setSelectedTastes)}>{item}</Chip>)}</div></div></div> : null}
    <div className="sticky-action"><Button type={step === 3 ? 'submit' : 'button'} onClick={step < 3 ? () => setStep((value) => value + 1) : undefined} disabled={saving}>{saving ? 'Saving…' : step === 3 ? 'Save preferences' : 'Continue'} <ArrowRight /></Button></div>
  </form>
}
